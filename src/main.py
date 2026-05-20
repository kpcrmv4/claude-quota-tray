"""
Claude Quota Tray — entry point.

A small system-tray app for Windows (and macOS/Linux) that polls Claude's
usage headers and displays the higher of session/weekly utilisation as a
coloured badge in the tray. Hover the icon for full details, right-click
for actions.
"""

import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional

import pystray

import config
import notifications
import settings as user_settings
import history
import sound
import theme as theme_mod
import accounts
import history_window
import status_window
import settings_dialogs
from i18n import LANGUAGES, set_language, t
from bar_widget import color_emoji, unicode_bar
from api_client import fetch_usage, format_reset, UsageSnapshot
from icon_renderer import render_icon
from token_reader import TokenError


REPO_URL = "https://github.com/kpcrmv4/claude-quota-tray"
CONSOLE_USAGE_URL = "https://console.anthropic.com/settings/usage"
CONSOLE_LIMITS_URL = "https://console.anthropic.com/settings/limits"


# --- State held across the lifetime of the tray icon ----------------------

class AppState:
    def __init__(self):
        self.token: Optional[str] = None
        self.token_error: Optional[str] = None
        self.snapshot: Optional[UsageSnapshot] = None
        self.burn: dict = {"session": {}, "weekly": {}}
        self.force_refresh = threading.Event()
        self.stop = threading.Event()
        self.fired_thresholds = {"session": set(), "weekly": set()}
        self.last_prune = 0.0
        self.active_account: Optional[dict] = None
        self.plan: Optional[str] = None
        self.paused_by_schedule = False

    @property
    def headline_pct(self) -> Optional[int]:
        """Number shown on the tray icon.

        Always the 5-hour figure because it resets in hours and is the
        most actionable. Weekly remains visible in tooltip, popup, menu,
        and history window.
        """
        if not self.snapshot or not self.snapshot.has_data:
            return None
        if self.snapshot.session_pct is not None:
            return self.snapshot.session_pct
        return self.snapshot.weekly_pct

    @property
    def is_error(self) -> bool:
        if self.token_error:
            return True
        if self.snapshot and not self.snapshot.ok:
            return True
        return False


state = AppState()


# --- Helpers --------------------------------------------------------------

def _current_theme() -> str:
    return theme_mod.effective_theme(user_settings.get("theme", "auto"))


def _current_icon_style() -> str:
    from icon_renderer import STYLES
    style = user_settings.get("icon_style", "frame")
    return style if style in STYLES else "frame"


def _thresholds() -> list[int]:
    val = user_settings.get("thresholds", config.NOTIFY_THRESHOLDS)
    return sorted({int(t) for t in val if isinstance(t, (int, float))})


def _within_schedule() -> bool:
    sched = user_settings.get("schedule", {}) or {}
    if not sched.get("enabled"):
        return True
    now = datetime.now()
    if now.weekday() not in sched.get("days", []):
        return False
    h = now.hour + now.minute / 60.0
    start = float(sched.get("start_hour", 0))
    end = float(sched.get("end_hour", 24))
    if start <= end:
        return start <= h < end
    # Wrap past midnight (e.g., 22-6)
    return h >= start or h < end


def _load_active_token() -> None:
    """Resolve the active account, token, and plan info."""
    try:
        acct = accounts.active_account()
        state.active_account = acct
        creds = accounts.get_credentials(acct)
        state.token = creds["token"]
        state.plan = creds.get("plan")
        state.token_error = None
    except TokenError as e:
        state.active_account = None
        state.token = None
        state.plan = None
        state.token_error = str(e)


# --- Background poller ----------------------------------------------------

def poll_loop(icon: pystray.Icon):
    """Outer wrapper that auto-restarts the inner loop on uncaught errors."""
    while not state.stop.is_set():
        try:
            _poll_loop_inner(icon)
            return  # Clean exit (stop set inside inner)
        except Exception:
            _log_action_error("poll_loop")
            # Brief pause so we don't hot-loop on a persistent failure
            state.force_refresh.clear()
            state.force_refresh.wait(timeout=15)


def _poll_loop_inner(icon: pystray.Icon):
    _load_active_token()
    _refresh_icon(icon)
    if state.token_error and state.token is None:
        # Without a token, sit idle but keep checking — user can configure
        # an account from the menu and we'll pick it up on next iteration.
        while not state.stop.is_set():
            state.force_refresh.clear()
            state.force_refresh.wait(timeout=30)
            _load_active_token()
            _refresh_icon(icon)
            if state.token:
                break
        if state.stop.is_set():
            return

    time.sleep(config.INITIAL_DELAY_SECONDS)

    while not state.stop.is_set():
        if not _within_schedule():
            state.paused_by_schedule = True
            _refresh_icon(icon)
        else:
            state.paused_by_schedule = False
            if state.token is None:
                _load_active_token()
            if state.token:
                snapshot = fetch_usage(state.token, model=config.MODEL)
                # Stale-token guard: Claude Code rotates OAuth access tokens
                # periodically. If our cached token was rotated out from under
                # us, the API returns 401/403. Re-read the credentials file
                # once and retry the poll — costs one wasted request per
                # rotation event, but keeps the tray live across rotations
                # without forcing the user to restart.
                if (snapshot.status_code in (401, 403)
                        and not snapshot.has_data):
                    _load_active_token()
                    if state.token:
                        snapshot = fetch_usage(state.token, model=config.MODEL)
                state.snapshot = snapshot
                acct_id = state.active_account["id"] if state.active_account else "unknown"
                history.record(acct_id, snapshot)
                state.burn = history.burn_rate(60, acct_id)
                _check_notifications(icon, snapshot)
            _refresh_icon(icon)

        _maybe_prune()
        interval = int(user_settings.get("poll_interval_seconds", config.POLL_INTERVAL_SECONDS))
        state.force_refresh.clear()
        state.force_refresh.wait(timeout=max(15, interval))


def _maybe_prune():
    now = time.time()
    if now - state.last_prune < 3600:
        return
    state.last_prune = now
    retention = int(user_settings.get("history_retention_days", 7))
    history.prune(retention)


def _refresh_icon(icon: pystray.Icon):
    try:
        icon.icon = render_icon(state.headline_pct, error=state.is_error,
                                theme=_current_theme(),
                                style=_current_icon_style())
    except Exception:
        _log_action_error("_refresh_icon:icon")
    try:
        # Win32 caps tooltip at 128 wide chars — _build_tooltip truncates,
        # but extra defence here in case a future caller forgets.
        icon.title = _build_tooltip()[:_TOOLTIP_MAX]
    except Exception:
        _log_action_error("_refresh_icon:title")
    try:
        icon.menu = build_menu()
        icon.update_menu()
    except Exception:
        _log_action_error("_refresh_icon:menu")


# Win32 tray tooltip (NOTIFYICONDATAW.szTip) is capped at 128 wide chars
# including the null terminator. Stay well under to leave headroom for
# the multi-line newline expansion Windows does internally.
_TOOLTIP_MAX = 120


def _truncate(text: str, limit: int = _TOOLTIP_MAX) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _build_tooltip() -> str:
    if state.token_error:
        return _truncate(f"{config.APP_NAME}\n{t('status.token_error_tooltip')}")
    if state.paused_by_schedule:
        return _truncate(f"{config.APP_NAME}\n{t('status.paused_tooltip')}")
    snap = state.snapshot
    if snap is None:
        return _truncate(f"{config.APP_NAME}\n{t('status.fetching_tooltip')}")
    if not snap.ok:
        return _truncate(
            f"{config.APP_NAME}\n"
            f"{t('status.error_tooltip', msg=snap.error or 'unknown')}"
        )

    # Compact tooltip — full details live in the popup / menu.
    # Build progressively so we can drop the lowest-priority bits if we
    # are running out of space.
    name = state.active_account["name"] if state.active_account else config.APP_NAME
    header = f"{name}"
    if state.plan:
        header += f" · {state.plan}"

    parts = []
    if snap.session_pct is not None:
        parts.append(
            f"{t('bar.session_short')} {snap.session_pct}% "
            f"→ {format_reset(snap.session_reset_seconds)}"
        )
    if snap.weekly_pct is not None:
        parts.append(
            f"{t('bar.weekly_short')} {snap.weekly_pct}% "
            f"→ {format_reset(snap.weekly_reset_seconds)}"
        )

    body = "\n".join(parts) if parts else t('status.no_headers')
    return _truncate(f"{header}\n{body}")


def _eta_summary() -> Optional[str]:
    bits = []
    for key, label in (("session", t('bar.session_short')),
                       ("weekly", t('bar.weekly_short'))):
        info = state.burn.get(key, {})
        eta = info.get("eta_seconds")
        rate = info.get("rate")
        if eta is not None and rate is not None:
            bits.append(t('bar.burn_full_in', label=label,
                          rate=rate, eta=format_reset(eta)))
    return " · ".join(bits) if bits else None


def _check_notifications(icon: pystray.Icon, snap: UsageSnapshot):
    if not snap.ok or not snap.has_data:
        return

    thresholds = _thresholds()
    play_sound = bool(user_settings.get("sound_alerts", True))
    pairs = [
        ("session", snap.session_pct, t('bar.session_short')),
        ("weekly", snap.weekly_pct, t('bar.weekly_short')),
    ]
    for key, pct, label in pairs:
        if pct is None:
            continue
        fired = state.fired_thresholds[key]
        fired.intersection_update({th for th in thresholds if pct >= th})
        for threshold in thresholds:
            if pct >= threshold and threshold not in fired:
                fired.add(threshold)
                notifications.notify(
                    icon,
                    t('toast.heads_up_title', app=config.APP_NAME),
                    t('toast.heads_up_body', label=label, pct=pct),
                )
                if play_sound:
                    sound.play_alert()


# --- Menu actions ---------------------------------------------------------

def action_refresh(icon, item):
    state.force_refresh.set()


def _log_action_error(where: str) -> None:
    try:
        log = Path.home() / ".claude-quota-tray" / "error.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {where}\n")
            f.write(traceback.format_exc())
    except Exception:
        pass


def action_show_status(icon, item):
    """Left-click action: open the compact status popup with progress bars.
    Falls back to the full history window if the popup fails to spawn."""
    if state.token_error:
        notifications.notify(icon,
                             t('toast.token_error_title', app=config.APP_NAME),
                             state.token_error[:200])
        return
    name = state.active_account["name"] if state.active_account else config.APP_NAME
    try:
        ok = status_window.show(name, get_data=_current_data)
    except Exception:
        _log_action_error("action_show_status:status_window")
        ok = False

    if ok:
        return

    # Fallback: open the proven history window instead.
    try:
        if state.active_account:
            history_window.show(
                state.active_account["id"],
                state.active_account["name"],
                get_data=_current_data,
            )
            return
    except Exception:
        _log_action_error("action_show_status:history_window")

    # Last resort: notification with current numbers.
    snap = state.snapshot
    parts = []
    if snap and snap.session_pct is not None:
        parts.append(f"{t('bar.session_short')}: {snap.session_pct}%")
    if snap and snap.weekly_pct is not None:
        parts.append(f"{t('bar.weekly_short')}: {snap.weekly_pct}%")
    notifications.notify(icon, config.APP_NAME,
                         " · ".join(parts) or t('status.no_data'))


def action_show_error(icon, item):
    msg = state.token_error or (state.snapshot.error if state.snapshot else None)
    if msg:
        notifications.notify(icon,
                             t('toast.error_title', app=config.APP_NAME),
                             msg[:200])


def action_quit(icon, item):
    state.stop.set()
    state.force_refresh.set()
    icon.stop()


def action_open_repo(icon, item):
    webbrowser.open(REPO_URL)


def action_open_console_usage(icon, item):
    webbrowser.open(CONSOLE_USAGE_URL)


def action_open_console_limits(icon, item):
    webbrowser.open(CONSOLE_LIMITS_URL)


def _current_data() -> dict:
    snap = state.snapshot
    return {
        "session_pct": snap.session_pct if snap else None,
        "weekly_pct": snap.weekly_pct if snap else None,
        "session_reset": snap.session_reset_seconds if snap else None,
        "weekly_reset": snap.weekly_reset_seconds if snap else None,
        "burn": state.burn,
        "plan": state.plan,
    }


def action_show_history(icon, item):
    if not state.active_account:
        notifications.notify(icon, config.APP_NAME, t('status.no_account'))
        return
    history_window.show(
        state.active_account["id"],
        state.active_account["name"],
        get_data=_current_data,
    )


def _on_settings_changed(icon: pystray.Icon):
    def _cb():
        state.fired_thresholds = {"session": set(), "weekly": set()}
        _load_active_token()
        state.force_refresh.set()
        try:
            _refresh_icon(icon)
        except Exception:
            pass
    return _cb


def action_manage_accounts(icon, item):
    settings_dialogs.open_accounts(_on_settings_changed(icon))


def action_edit_schedule(icon, item):
    settings_dialogs.open_schedule(_on_settings_changed(icon))


def action_edit_thresholds(icon, item):
    settings_dialogs.open_thresholds(_on_settings_changed(icon))


def _make_switch_account(account_id: str):
    def _do(icon, item):
        accounts.set_active(account_id)
        state.fired_thresholds = {"session": set(), "weekly": set()}
        _load_active_token()
        state.force_refresh.set()
        _refresh_icon(icon)
    return _do


def _make_set_threshold_preset(preset: list[int]):
    def _do(icon, item):
        user_settings.update(thresholds=preset)
        state.fired_thresholds = {"session": set(), "weekly": set()}
        _refresh_icon(icon)
    return _do


def _make_set_theme(value: str):
    def _do(icon, item):
        user_settings.update(theme=value)
        _refresh_icon(icon)
    return _do


def _make_set_icon_style(value: str):
    def _do(icon, item):
        user_settings.update(icon_style=value)
        _refresh_icon(icon)
    return _do


def _make_set_interval(seconds: int):
    def _do(icon, item):
        user_settings.update(poll_interval_seconds=seconds)
        state.force_refresh.set()
        _refresh_icon(icon)
    return _do


def _restart_app(icon) -> None:
    """Spawn a replacement instance, then shut this one down.

    Used after settings changes that require a full UI rebuild (e.g.,
    language) because pystray on Windows can't reliably swap an active
    Win32 popup menu from a non-message-loop thread.
    """
    try:
        if getattr(sys, "frozen", False):
            # Bundled exe — just relaunch self
            args = [sys.executable] + sys.argv[1:]
        else:
            args = [sys.executable] + sys.argv
        kwargs: dict = {"close_fds": True}
        if sys.platform == "win32":
            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(args, **kwargs)
    except Exception:
        _log_action_error("restart_spawn")
        return

    # Brief delay so the replacement instance has time to come up before
    # we remove our tray icon — avoids a visible gap.
    time.sleep(0.6)
    state.stop.set()
    state.force_refresh.set()
    try:
        icon.stop()
    except Exception:
        pass


def _make_set_language(code: str):
    def _do(icon, item):
        if code == user_settings.get("language"):
            return
        set_language(code)
        notifications.notify(
            icon,
            config.APP_NAME,
            f"{t('common.save')}: {LANGUAGES.get(code, code)}",
        )
        # Restart on a worker thread so we don't block this menu callback
        # while we sleep and then tear down pystray.
        threading.Thread(
            target=_restart_app, args=(icon,), daemon=True,
        ).start()
    return _do


def action_toggle_sound(icon, item):
    cur = bool(user_settings.get("sound_alerts", True))
    user_settings.update(sound_alerts=not cur)
    _refresh_icon(icon)


def action_toggle_schedule(icon, item):
    sched = dict(user_settings.get("schedule", {}) or {})
    sched["enabled"] = not bool(sched.get("enabled"))
    user_settings.update(schedule=sched)
    state.force_refresh.set()
    _refresh_icon(icon)


# --- Menu construction ----------------------------------------------------

def build_menu():
    return pystray.Menu(
        pystray.MenuItem(
            lambda item: _menu_headline_text(),
            None,
            enabled=False,
        ),
        pystray.MenuItem(
            lambda item: _menu_session_text(),
            None,
            enabled=False,
            visible=lambda item: bool(_menu_session_text()),
        ),
        pystray.MenuItem(
            lambda item: _menu_weekly_text(),
            None,
            enabled=False,
            visible=lambda item: bool(_menu_weekly_text()),
        ),
        pystray.MenuItem(
            lambda item: _menu_burn_text(),
            None,
            enabled=False,
            visible=lambda item: bool(_menu_burn_text()),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t('menu.show_status'), action_show_status, default=True),
        pystray.MenuItem(t('menu.show_history'), action_show_history),
        pystray.MenuItem(t('menu.refresh_now'), action_refresh),
        pystray.MenuItem(
            t('menu.show_last_error'),
            action_show_error,
            visible=lambda item: state.is_error,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t('menu.account'), _build_account_menu()),
        pystray.MenuItem(t('menu.settings'), _build_settings_menu()),
        pystray.MenuItem(t('menu.open_console'), _build_console_menu()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Powered by KPWebappStudio", action_open_repo),
        pystray.MenuItem(t('menu.quit', app=config.APP_NAME), action_quit),
    )


def _build_account_menu():
    items = []
    active = state.active_account
    active_id = active["id"] if active else None
    for acct in accounts.list_accounts():
        items.append(pystray.MenuItem(
            acct.get("name", "Account"),
            _make_switch_account(acct["id"]),
            checked=lambda item, aid=acct["id"]: aid == active_id,
            radio=True,
        ))
    if items:
        items.append(pystray.Menu.SEPARATOR)
    items.append(pystray.MenuItem(t('menu.manage_accounts'), action_manage_accounts))
    return pystray.Menu(*items)


def _build_settings_menu():
    cur_thresholds = _thresholds()
    presets = [
        (t('menu.thresholds_quiet'), [95]),
        (t('menu.thresholds_default'), [80, 95]),
        (t('menu.thresholds_sensitive'), [50, 75, 90]),
    ]
    threshold_items = [
        pystray.MenuItem(
            label,
            _make_set_threshold_preset(values),
            checked=lambda item, v=values: list(v) == cur_thresholds,
            radio=True,
        )
        for label, values in presets
    ]

    cur_theme = user_settings.get("theme", "auto")
    theme_items = [
        pystray.MenuItem(
            label,
            _make_set_theme(value),
            checked=lambda item, v=value: v == cur_theme,
            radio=True,
        )
        for label, value in (
            (t('menu.theme_auto'), "auto"),
            (t('menu.theme_light'), "light"),
            (t('menu.theme_dark'), "dark"),
        )
    ]

    cur_style = _current_icon_style()
    style_items = [
        pystray.MenuItem(
            label,
            _make_set_icon_style(value),
            checked=lambda item, v=value: v == cur_style,
            radio=True,
        )
        for label, value in (
            (t('menu.style_frame'), "frame"),
            (t('menu.style_solid'), "solid"),
            (t('menu.style_donut'), "donut"),
            (t('menu.style_bar'), "bar"),
        )
    ]

    cur_interval = int(user_settings.get("poll_interval_seconds", 60))
    interval_items = [
        pystray.MenuItem(
            label,
            _make_set_interval(seconds),
            checked=lambda item, s=seconds: s == cur_interval,
            radio=True,
        )
        for label, seconds in (
            (t('menu.interval_30s'), 30),
            (t('menu.interval_1m'), 60),
            (t('menu.interval_2m'), 120),
            (t('menu.interval_5m'), 300),
        )
    ]

    from i18n import current_language
    cur_lang = current_language()
    language_items = [
        pystray.MenuItem(
            label,
            _make_set_language(code),
            checked=lambda item, c=code: c == cur_lang,
            radio=True,
        )
        for code, label in LANGUAGES.items()
    ]

    sched = user_settings.get("schedule", {}) or {}
    sched_label = t(
        'menu.pause_outside',
        start=int(sched.get('start_hour', 9)),
        end=int(sched.get('end_hour', 18)),
    )

    threshold_items.append(pystray.Menu.SEPARATOR)
    threshold_items.append(pystray.MenuItem(t('menu.thresholds_custom'),
                                            action_edit_thresholds))

    return pystray.Menu(
        pystray.MenuItem(t('menu.alert_thresholds'),
                         pystray.Menu(*threshold_items)),
        pystray.MenuItem(
            t('menu.sound_alerts'),
            action_toggle_sound,
            checked=lambda item: bool(user_settings.get("sound_alerts", True)),
        ),
        pystray.MenuItem(
            sched_label,
            action_toggle_schedule,
            checked=lambda item: bool(
                (user_settings.get("schedule", {}) or {}).get("enabled")
            ),
        ),
        pystray.MenuItem(t('menu.schedule_settings'), action_edit_schedule),
        pystray.MenuItem(t('menu.icon_theme'), pystray.Menu(*theme_items)),
        pystray.MenuItem(t('menu.icon_style'), pystray.Menu(*style_items)),
        pystray.MenuItem(t('menu.poll_interval'),
                         pystray.Menu(*interval_items)),
        pystray.MenuItem(t('menu.language'), pystray.Menu(*language_items)),
    )


def _build_console_menu():
    return pystray.Menu(
        pystray.MenuItem(t('menu.console_usage'), action_open_console_usage),
        pystray.MenuItem(t('menu.console_limits'), action_open_console_limits),
    )


def _menu_headline_text() -> str:
    snap = state.snapshot
    if state.token_error:
        return t('status.token_error')
    if state.paused_by_schedule:
        return t('status.paused')
    if snap is None:
        return t('status.fetching')
    if not snap.ok:
        return t('status.api_error')
    name = state.active_account["name"] if state.active_account else config.APP_NAME
    if state.plan:
        return f"● {name} · {state.plan}"
    return f"● {name}"


def _menu_session_text() -> str:
    snap = state.snapshot
    if not snap or not snap.ok or snap.session_pct is None:
        return ""
    pct = snap.session_pct
    return (
        f"{color_emoji(pct)} {t('bar.session_short')}  {unicode_bar(pct)}  {pct:>3}%  "
        f"· {t('bar.resets_in', time=format_reset(snap.session_reset_seconds))}"
    )


def _menu_weekly_text() -> str:
    snap = state.snapshot
    if not snap or not snap.ok or snap.weekly_pct is None:
        return ""
    pct = snap.weekly_pct
    return (
        f"{color_emoji(pct)} {t('bar.weekly_short')}  {unicode_bar(pct)}  {pct:>3}%  "
        f"· {t('bar.resets_in', time=format_reset(snap.weekly_reset_seconds))}"
    )


def _menu_burn_text() -> str:
    bits = []
    for key, label in (("session", t('bar.session_short')),
                       ("weekly", t('bar.weekly_short'))):
        info = state.burn.get(key, {})
        rate = info.get("rate")
        eta = info.get("eta_seconds")
        if rate is None:
            continue
        if eta is not None:
            bits.append(f"{label}: +{rate:.0f}%/h → {format_reset(eta)}")
        else:
            bits.append(f"{label}: +{rate:.0f}%/h")
    return " · ".join(bits)


# --- Entry point ----------------------------------------------------------

def _redirect_stderr_to_log() -> None:
    """When running under pythonw.exe there is no console; redirect stderr to
    a file so we can see unhandled tracebacks instead of the process
    silently disappearing."""
    try:
        log_path = Path.home() / ".claude-quota-tray" / "error.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stream = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stderr = stream
        sys.stderr.write(
            f"\n=== started {time.strftime('%Y-%m-%d %H:%M:%S')} "
            f"pid={__import__('os').getpid()} ===\n"
        )
    except Exception:
        pass


def main():
    _redirect_stderr_to_log()

    try:
        user_settings.load()
        notifications.init(config.APP_NAME)

        icon = pystray.Icon(
            config.APP_ID,
            icon=render_icon(None, theme=_current_theme(),
                             style=_current_icon_style()),
            title=f"{config.APP_NAME}\nStarting…",
            menu=build_menu(),
        )

        poller = threading.Thread(target=poll_loop, args=(icon,), daemon=True)
        poller.start()

        icon.run()
        try:
            sys.stderr.write(
                f"=== icon.run() returned cleanly "
                f"{time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
            )
        except Exception:
            pass
    except Exception:
        try:
            sys.stderr.write(
                f"\n!!! FATAL {time.strftime('%Y-%m-%d %H:%M:%S')} !!!\n"
            )
            traceback.print_exc(file=sys.stderr)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
