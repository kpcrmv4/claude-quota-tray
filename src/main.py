"""
Claude Quota Tray — entry point.

Windows system-tray app that polls Claude usage headers and shows the
5-hour limit as a coloured badge. OAuth is discovered from Claude Desktop,
Claude Code, or env vars (see auth_discovery.py). Hover for details,
right-click for actions.
"""

import os
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

import app_paths
import app_platform
import config
import notifications
import settings as user_settings
import updater
import history
import sound
import theme as theme_mod
import accounts
import history_window
import status_window
import settings_dialogs
import desktop_widget
from i18n import LANGUAGES, set_language, t
from bar_widget import color_emoji, refresh_color_constants, unicode_bar
from api_client import fetch_usage, format_reset, UsageSnapshot
from icon_renderer import render_icon
from token_reader import TokenError


def _repo_url() -> str:
    spec = user_settings.get("update_github_repo") or config.DEFAULT_UPDATE_REPO
    try:
        owner, repo = updater.parse_github_repo(str(spec))
        return f"https://github.com/{owner}/{repo}"
    except ValueError:
        return f"https://github.com/{config.DEFAULT_UPDATE_REPO}"
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
        self.fired_thresholds = {"session": set(), "weekly": set(), "opus": set()}
        self.last_prune = 0.0
        self.active_account: Optional[dict] = None
        self.plan: Optional[str] = None
        self.paused_by_schedule = False
        self.setup_notice_shown = False
        self.token_expires_at: Optional[float] = None  # epoch seconds; None = unknown
        self.token_source: Optional[str] = None         # which auth source is active
        self.reset_notified = {"session": False, "weekly": False, "opus": False}
        self.auth_retry_after: float = 0.0             # epoch seconds; 0 = no retry pending
        self.auth_401_notified: bool = False            # suppress duplicate toasts
        self.bad_tokens: set = set()                    # token strings rejected with 401
        self.last_poll_at: float = 0.0
        self.poll_fail_streak: int = 0
        self.update_check_done: bool = False

    @property
    def headline_pct(self) -> Optional[int]:
        """Number shown on the tray icon (metric from settings)."""
        if not self.snapshot or not self.snapshot.has_data:
            return None
        s = self.snapshot.session_pct
        w = self.snapshot.weekly_pct
        o = self.snapshot.opus_pct
        metric = user_settings.get("tray_icon_metric", "session")
        if metric == "weekly":
            return w if w is not None else s
        if metric == "max":
            vals = [v for v in (s, w, o) if v is not None]
            return max(vals) if vals else None
        return s if s is not None else w

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
    return sorted({int(x) for x in val if isinstance(x, (int, float))})


def _thresholds_for(key: str) -> list[int]:
    specific = user_settings.get(f"thresholds_{key}")
    if specific:
        return sorted({int(x) for x in specific if isinstance(x, (int, float))})
    return _thresholds()


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


def _maybe_show_setup_notice(icon: pystray.Icon) -> None:
    """One-time toast when Claude Code auth is missing."""
    if state.setup_notice_shown or state.token:
        return
    state.setup_notice_shown = True
    notifications.notify(
        icon,
        t("toast.setup_title", app=config.APP_NAME),
        t("toast.setup_body"),
    )


def _is_auth_failure(snapshot) -> bool:
    """True if a snapshot failed because the token is invalid/expired (401/403)."""
    if snapshot.ok:
        return False
    if getattr(snapshot, "http_status", None) in (401, 403):
        return True
    err = snapshot.error or ""
    return "401" in err or "403" in err


_TOKEN_REFRESH_AHEAD_SECS = 300  # reload token 5 min before it expires


def _load_active_token() -> None:
    """Resolve the active account, token, and plan info."""
    try:
        acct = accounts.active_account()
        state.active_account = acct
        creds = accounts.get_credentials(acct, exclude_tokens=state.bad_tokens or None)
        state.token = creds["token"]
        state.plan = creds.get("plan")
        state.token_source = creds.get("source")
        state.token_error = None
        state.auth_retry_after = 0.0
        state.auth_401_notified = False
        # Extract expiry for proactive refresh (feature 4)
        raw = creds.get("raw") or {}
        expires_ms = raw.get("expiresAt")
        state.token_expires_at = (
            float(expires_ms) / 1000.0
            if isinstance(expires_ms, (int, float))
            else None
        )
    except TokenError as e:
        state.active_account = None
        state.token = None
        state.plan = None
        state.token_source = None
        state.token_error = str(e)
        state.token_expires_at = None


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
        _maybe_show_setup_notice(icon)
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

            # Feature 4: proactive refresh when token is near expiry
            if (
                state.token is not None
                and state.token_expires_at is not None
                and state.token_expires_at - time.time() < _TOKEN_REFRESH_AHEAD_SECS
            ):
                _load_active_token()

            # Feature 3: backoff retry — reload token once the wait has elapsed
            if state.auth_retry_after and time.time() >= state.auth_retry_after:
                state.auth_retry_after = 0.0
                _load_active_token()

            if state.token is None:
                _load_active_token()

            if state.token:
                # Guard the whole fetch→record→notify path: a network blip,
                # token loss, an unexpected API schema change, or a SQLite
                # hiccup must never kill the poller — log it and back off.
                try:
                    snapshot = fetch_usage(state.token, model=config.MODEL)
                    if _is_auth_failure(snapshot):
                        failed_token = state.token
                        # Remember this token as bad and try the next source.
                        if failed_token:
                            state.bad_tokens.add(failed_token)
                        _load_active_token()
                        if state.token and state.token != failed_token:
                            # A different source had a usable token — retry it
                            # now instead of backing off on the dead one.
                            state.force_refresh.set()
                            continue
                        if not state.auth_401_notified:
                            state.auth_401_notified = True
                            notifications.notify(
                                icon,
                                t('toast.auth_expired_title', app=config.APP_NAME),
                                t('toast.auth_expired_body'),
                            )
                        if not state.auth_retry_after:
                            state.auth_retry_after = time.time() + 30.0
                        state.poll_fail_streak = min(state.poll_fail_streak + 1, 8)
                    else:
                        if snapshot.ok:
                            state.poll_fail_streak = 0
                            state.last_poll_at = time.time()
                        elif snapshot.error:
                            state.poll_fail_streak = min(state.poll_fail_streak + 1, 8)
                    state.snapshot = snapshot
                    acct_id = state.active_account["id"] if state.active_account else "unknown"
                    history.record(acct_id, snapshot)
                    state.burn = history.burn_rate(60, acct_id)
                    _check_notifications(icon, snapshot)
                    _check_reset_notifications(icon, snapshot)
                except Exception:
                    _log_action_error("poll_iteration")
                    state.poll_fail_streak = min(state.poll_fail_streak + 1, 8)
            _refresh_icon(icon)
            if not state.update_check_done:
                state.update_check_done = True
                _maybe_notify_update(icon)

        _maybe_prune()
        configured = int(user_settings.get("poll_interval_seconds", config.POLL_INTERVAL_SECONDS))
        base = _compute_auto_interval() if configured == 0 else configured
        if state.poll_fail_streak > 0:
            interval = min(600, base * (2 ** min(state.poll_fail_streak, 4)))
        else:
            interval = base
        state.force_refresh.clear()
        state.force_refresh.wait(timeout=max(15, interval))


def _maybe_prune():
    now = time.time()
    if now - state.last_prune < 3600:
        return
    state.last_prune = now
    retention = int(user_settings.get("history_retention_days", 7))
    history.prune(retention)


def _refresh_icon(icon: pystray.Icon, *, update_menu: bool = False) -> None:
    """Refresh tray visuals.

    On Windows, icon.menu / update_menu() must not run from the poll thread —
    that race crashes the Win32 message loop and the tray icon vanishes.
    The poller only updates the badge image + tooltip; menu rebuilds happen
    from menu callbacks (main/message thread) or when update_menu=True.
    """
    refresh_color_constants()
    try:
        icon.icon = render_icon(state.headline_pct, error=state.is_error,
                                theme=_current_theme(),
                                style=_current_icon_style())
    except Exception:
        _log_action_error("_refresh_icon:icon")
    try:
        icon.title = _build_tooltip()[:_TOOLTIP_MAX]
    except Exception:
        _log_action_error("_refresh_icon:title")
    try:
        desktop_widget.refresh(_current_data)
    except Exception:
        pass
    if update_menu:
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
    if snap.opus_pct is not None:
        parts.append(
            f"{t('bar.opus_short')} {snap.opus_pct}% "
            f"→ {format_reset(snap.opus_reset_seconds)}"
        )

    body = "\n".join(parts) if parts else t('status.no_headers')
    if state.last_poll_at > 0:
        ago = int(time.time() - state.last_poll_at)
        if ago < 60:
            ago_s = f"{ago}s"
        elif ago < 3600:
            ago_s = f"{ago // 60}m"
        else:
            ago_s = f"{ago // 3600}h"
        body += "\n" + t("status.last_poll", ago=ago_s)
    # Surface token expiry only when it's close enough to act on.
    if state.token_expires_at is not None:
        left = state.token_expires_at - time.time()
        if left <= 86400:
            note = (t('health.expired') if left <= 0
                    else t('health.expires_in', time=format_reset(int(left))))
            body += "\n" + f"{t('health.expires')} {note}"
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
    snooze = float(user_settings.get("alert_snooze_until") or 0)
    if snooze > time.time():
        return

    play_sound = bool(user_settings.get("sound_alerts", True))
    pairs = [
        ("session", snap.session_pct, t('bar.session_short')),
        ("weekly", snap.weekly_pct, t('bar.weekly_short')),
        ("opus", snap.opus_pct, t('bar.opus_short')),
    ]
    for key, pct, label in pairs:
        if pct is None:
            continue
        thresholds = _thresholds_for(key)
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


# Only bother announcing a reset for a limit the user actually leaned on.
_RESET_NOTICE_MIN_PCT = 40


def _check_reset_notifications(icon: pystray.Icon, snap: UsageSnapshot) -> None:
    """Notify once when a meaningfully-used limit is about to reset.

    'About to' = within ``reset_notice_minutes`` (default 10). Re-arms when the
    reset window rolls over (reset_seconds climbs back up), so each cycle fires
    at most one toast per limit.
    """
    if not snap.ok or not snap.has_data:
        return
    if not bool(user_settings.get("notify_before_reset", True)):
        return
    snooze = float(user_settings.get("alert_snooze_until") or 0)
    if snooze > time.time():
        return
    window = int(user_settings.get("reset_notice_minutes", 10)) * 60

    triples = [
        ("session", snap.session_pct, snap.session_reset_seconds, t('bar.session_short')),
        ("weekly", snap.weekly_pct, snap.weekly_reset_seconds, t('bar.weekly_short')),
        ("opus", snap.opus_pct, snap.opus_reset_seconds, t('bar.opus_short')),
    ]
    for key, pct, reset_secs, label in triples:
        if pct is None or reset_secs is None:
            continue
        if reset_secs > window:
            # Window is far out again → re-arm for the next cycle.
            state.reset_notified[key] = False
            continue
        if pct < _RESET_NOTICE_MIN_PCT:
            continue
        if not state.reset_notified.get(key):
            state.reset_notified[key] = True
            notifications.notify(
                icon,
                t('toast.reset_soon_title', app=config.APP_NAME),
                t('toast.reset_soon_body', label=label, pct=pct,
                  time=format_reset(reset_secs)),
            )


# Auto poll interval (settings poll_interval_seconds == 0). Bounds in seconds.
_AUTO_MIN, _AUTO_MAX = 30, 300


def _compute_auto_interval() -> int:
    """Adaptive poll interval from current usage + burn rate.

    Polls fast when usage is high, climbing quickly, or a window is about to
    reset (to catch the drop); slows down when usage is low and flat.
    """
    snap = state.snapshot
    if snap is None or not snap.has_data:
        return 60
    pcts = [p for p in (snap.session_pct, snap.weekly_pct, snap.opus_pct) if p is not None]
    pct = max(pcts) if pcts else 0

    max_rate = 0.0
    for info in (state.burn or {}).values():
        rate = (info or {}).get("rate")
        if rate:
            max_rate = max(max_rate, rate)

    soonest_reset = min(
        [r for r in (snap.session_reset_seconds, snap.weekly_reset_seconds,
                     snap.opus_reset_seconds) if r is not None],
        default=None,
    )

    if pct >= 90 or max_rate >= 15 or (soonest_reset is not None and soonest_reset <= 120):
        return _AUTO_MIN
    if pct >= 70 or max_rate >= 5:
        return 45
    if pct < 40 and max_rate < 1:
        return _AUTO_MAX
    return 90


# --- Menu actions ---------------------------------------------------------

def action_refresh(icon, item):
    state.force_refresh.set()
    _refresh_icon(icon, update_menu=True)


def _log_action_error(where: str) -> None:
    try:
        log = Path.home() / ".claude-quota-tray" / "error.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {where}\n")
            f.write(traceback.format_exc())
    except Exception:
        pass


def _log_info(message: str) -> None:
    """Append a single timestamped info line to the shared log file.

    Used for noteworthy-but-not-fatal events (e.g. an OAuth token rotation
    that we recovered from) so they can be confirmed after the fact."""
    try:
        log = Path.home() / ".claude-quota-tray" / "error.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
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

    def _open_history():
        if state.active_account:
            history_window.show(
                state.active_account["id"],
                state.active_account["name"],
                get_data=_current_data,
            )

    try:
        ok = status_window.show(name, get_data=_current_data, on_open_history=_open_history)
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


def action_open_error_log(icon, item):
    log = Path.home() / ".claude-quota-tray" / "error.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    if not log.exists():
        log.write_text("", encoding="utf-8")
    try:
        app_platform.open_path(log)
    except Exception as e:
        notifications.notify(icon, config.APP_NAME, str(e)[:180])


def action_copy_status(icon, item):
    text = _build_tooltip().replace("\n", " | ")
    try:
        import tkinter as tk
        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
        notifications.notify(icon, config.APP_NAME, t("toast.status_copied"))
    except Exception as e:
        notifications.notify(icon, config.APP_NAME, str(e)[:120])


def action_snooze_alerts(icon, item):
    user_settings.update(alert_snooze_until=time.time() + 3600)
    notifications.notify(icon, config.APP_NAME, t("toast.alerts_snoozed"))


def _sync_desktop_widget(icon: pystray.Icon) -> None:
    dw = user_settings.get("desktop_widget") or {}
    if dw.get("enabled") and desktop_widget.is_supported():
        desktop_widget.show(_current_data, lambda: action_show_status(icon, None))
    else:
        desktop_widget.hide()


def action_toggle_desktop_widget(icon, item):
    dw = dict(user_settings.get("desktop_widget") or {})
    dw["enabled"] = not bool(dw.get("enabled"))
    user_settings.update(desktop_widget=dw)
    _sync_desktop_widget(icon)
    _refresh_icon(icon, update_menu=True)


def action_toggle_notify_on_update(icon, item):
    user_settings.update(notify_on_update=not bool(user_settings.get("notify_on_update", True)))
    _refresh_icon(icon, update_menu=True)


def _maybe_notify_update(icon: pystray.Icon) -> None:
    if not bool(user_settings.get("notify_on_update", True)):
        return

    def work():
        try:
            result = updater.check_for_update(_update_repo_spec())
            if result.error or not result.latest or not result.update_available:
                return
            notifications.notify(
                icon,
                config.APP_NAME,
                t("toast.update_available", version=result.latest.version),
            )
        except Exception:
            pass

    threading.Thread(target=work, daemon=True).start()


def action_quit(icon, item):
    desktop_widget.hide()
    state.stop.set()
    state.force_refresh.set()
    icon.stop()


def action_restart(icon, item):
    """Right-click menu: relaunch the app (picks up a fresh token + new code).

    Runs on a worker thread because _restart_app sleeps briefly and then tears
    down pystray, which must not block this menu callback / message loop.
    """
    threading.Thread(
        target=_restart_app, args=(icon,), daemon=True,
    ).start()


def _try_open_claude_desktop() -> bool:
    return app_platform.open_claude_desktop()


def action_reauth(icon, item):
    """Re-authenticate: reload token immediately; open Claude Desktop if needed."""
    state.auth_retry_after = 0.0
    state.auth_401_notified = False
    state.bad_tokens.clear()
    _load_active_token()
    if state.token:
        notifications.notify(icon, config.APP_NAME, t('toast.reauth_ok'))
        state.force_refresh.set()
        return
    # Token still missing — open Claude Desktop and retry after 15 s
    _try_open_claude_desktop()
    notifications.notify(
        icon,
        t('toast.reauth_title', app=config.APP_NAME),
        t('toast.reauth_body'),
    )
    def _delayed_retry():
        state.stop.wait(15)
        if state.stop.is_set():
            return
        _load_active_token()
        if state.token:
            notifications.notify(icon, config.APP_NAME, t('toast.reauth_ok'))
        else:
            notifications.notify(
                icon,
                t('toast.error_title', app=config.APP_NAME),
                t('toast.reauth_failed'),
            )
        state.force_refresh.set()
    threading.Thread(target=_delayed_retry, daemon=True).start()


def action_open_repo(icon, item):
    webbrowser.open(_repo_url())


def _update_repo_spec() -> str:
    return str(user_settings.get("update_github_repo") or config.DEFAULT_UPDATE_REPO)


def _launch_bat(path: Path) -> None:
    app_platform.open_path(path)


def action_check_update(icon, item):
    notifications.notify(icon, config.APP_NAME, t("toast.update_checking"))

    def work():
        result = updater.check_for_update(_update_repo_spec())
        if result.error:
            notifications.notify(
                icon,
                config.APP_NAME,
                t("toast.update_error", msg=result.error[:180]),
            )
            return
        if result.latest and result.update_available:
            notifications.notify(
                icon,
                config.APP_NAME,
                t("toast.update_available", version=result.latest.version),
            )
        elif result.latest:
            notifications.notify(
                icon,
                config.APP_NAME,
                t("toast.update_up_to_date", version=result.latest.version),
            )
        elif result.no_releases:
            notifications.notify(
                icon,
                config.APP_NAME,
                t("toast.update_no_releases"),
            )

    threading.Thread(target=work, daemon=True).start()


def _spawn_apply_update_and_quit(icon: pystray.Icon) -> None:
    root = app_paths.project_root()
    script = app_paths.update_runner_script()
    py = app_paths.venv_python()
    if py and script.is_file():
        popen_kw: dict = {"cwd": root, "close_fds": True, **app_platform.detached_popen_kwargs()}
        subprocess.Popen([str(py), str(script), "--apply"], **popen_kw)
        action_quit(icon, None)
        return

    def work():
        try:
            msg = updater.apply_update(
                root,
                _update_repo_spec(),
                prefer_exe=app_paths.is_frozen() and not app_paths.is_source_install(),
            )
            notifications.notify(
                icon, config.APP_NAME, t("toast.update_applied", msg=msg[:200])
            )
            if "after you quit" in msg.lower():
                action_quit(icon, None)
        except Exception as e:
            notifications.notify(
                icon, config.APP_NAME, t("toast.update_error", msg=str(e)[:180])
            )

    threading.Thread(target=work, daemon=True).start()


def action_apply_update(icon, item):
    settings_dialogs.confirm_apply_update(
        lambda: _spawn_apply_update_and_quit(icon)
    )


def action_configure_update_source(icon, item):
    settings_dialogs.open_update_source(_on_settings_changed(icon))


def action_open_releases(icon, item):
    result = updater.check_for_update(_update_repo_spec())
    url = result.latest.html_url if result.latest else _repo_url() + "/releases"
    webbrowser.open(url)


def action_open_install_folder(icon, item):
    _launch_bat(app_paths.project_root())


def action_run_setup(icon, item):
    path = app_paths.maintenance_scripts().get("setup")
    if path:
        _launch_bat(path)
    else:
        notifications.notify(icon, config.APP_NAME, t("toast.update_error", msg="Setup.bat not found"))


def action_run_update_bat(icon, item):
    path = app_paths.maintenance_scripts().get("update")
    if path:
        _launch_bat(path)
    else:
        action_apply_update(icon, item)


def action_run_uninstall(icon, item):
    path = app_paths.maintenance_scripts().get("uninstall")
    if not path:
        notifications.notify(icon, config.APP_NAME, t("toast.update_error", msg="Uninstall.bat not found"))
        return

    settings_dialogs.confirm_uninstall(lambda: _launch_bat(path))


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
        "opus_pct": snap.opus_pct if snap else None,
        "opus_reset": snap.opus_reset_seconds if snap else None,
        "burn": state.burn,
        "plan": state.plan,
        "token_source": state.token_source,
        "token_expires_at": state.token_expires_at,
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


def _export_summary(icon, days: int, filename: str) -> None:
    if not state.active_account:
        notifications.notify(icon, config.APP_NAME, t('status.no_account'))
        return

    def work():
        try:
            # So future summaries actually cover the period, make sure history
            # is retained at least as long as the report window. Transparent:
            # only bumps upward and tells the user when it does.
            retention = int(user_settings.get("history_retention_days", 7))
            if retention < days:
                user_settings.update(history_retention_days=days + 1)
                notifications.notify(
                    icon, config.APP_NAME,
                    t('toast.summary_retention', days=days + 1),
                )

            out = user_settings.SETTINGS_DIR / filename
            result = history.export_period_summary(
                out,
                state.active_account["name"],
                days,
                state.active_account["id"],
                threshold=(_thresholds_for("session") or [80])[0],
            )
            if result is None:
                notifications.notify(icon, config.APP_NAME, t('toast.summary_empty'))
                return
            notifications.notify(
                icon, config.APP_NAME,
                t('toast.summary_saved', path=str(result)),
            )
            try:
                app_platform.open_path(result)
            except Exception:
                pass
        except Exception:
            _log_action_error("export_summary")

    threading.Thread(target=work, daemon=True).start()


def action_export_weekly_summary(icon, item):
    _export_summary(icon, 7, "weekly-summary.md")


def action_export_monthly_summary(icon, item):
    _export_summary(icon, 30, "monthly-summary.md")


def _on_settings_changed(icon: pystray.Icon):
    def _cb():
        state.fired_thresholds = {"session": set(), "weekly": set(), "opus": set()}
        state.bad_tokens.clear()
        _load_active_token()
        state.force_refresh.set()
        _sync_desktop_widget(icon)
        try:
            _refresh_icon(icon, update_menu=True)
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
        state.fired_thresholds = {"session": set(), "weekly": set(), "opus": set()}
        state.bad_tokens.clear()
        _load_active_token()
        state.force_refresh.set()
        _refresh_icon(icon, update_menu=True)
    return _do


def _make_set_threshold_preset(preset: list[int]):
    def _do(icon, item):
        user_settings.update(
            thresholds=preset,
            thresholds_session=preset,
            thresholds_weekly=preset,
        )
        state.fired_thresholds = {"session": set(), "weekly": set(), "opus": set()}
        _refresh_icon(icon, update_menu=True)
    return _do


def _make_set_tray_metric(value: str):
    def _do(icon, item):
        user_settings.update(tray_icon_metric=value)
        _refresh_icon(icon, update_menu=True)
    return _do


def _make_set_theme(value: str):
    def _do(icon, item):
        user_settings.update(theme=value)
        refresh_color_constants()
        _refresh_icon(icon, update_menu=True)
    return _do


def _make_set_icon_style(value: str):
    def _do(icon, item):
        user_settings.update(icon_style=value)
        _refresh_icon(icon, update_menu=True)
    return _do


def _make_set_interval(seconds: int):
    def _do(icon, item):
        user_settings.update(poll_interval_seconds=seconds)
        state.force_refresh.set()
        _refresh_icon(icon, update_menu=True)
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
        kwargs: dict = {"close_fds": True, **app_platform.detached_popen_kwargs()}
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
    _refresh_icon(icon, update_menu=True)


def action_toggle_schedule(icon, item):
    sched = dict(user_settings.get("schedule", {}) or {})
    sched["enabled"] = not bool(sched.get("enabled"))
    user_settings.update(schedule=sched)
    state.force_refresh.set()
    _refresh_icon(icon, update_menu=True)


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
            lambda item: _menu_opus_text(),
            None,
            enabled=False,
            visible=lambda item: bool(_menu_opus_text()),
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
        pystray.MenuItem(t('menu.weekly_summary'), action_export_weekly_summary),
        pystray.MenuItem(t('menu.monthly_summary'), action_export_monthly_summary),
        pystray.MenuItem(t('menu.refresh_now'), action_refresh),
        pystray.MenuItem(t('menu.copy_status'), action_copy_status),
        pystray.MenuItem(t('menu.snooze_alerts'), action_snooze_alerts),
        pystray.MenuItem(t('menu.restart'), action_restart),
        pystray.MenuItem(
            t('menu.show_last_error'),
            action_show_error,
            visible=lambda item: state.is_error,
        ),
        pystray.MenuItem(t('menu.open_error_log'), action_open_error_log),
        pystray.MenuItem(
            t('menu.reauth'),
            action_reauth,
            visible=lambda item: state.is_error or state.token_error is not None,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t('menu.account'), _build_account_menu()),
        pystray.MenuItem(t('menu.settings'), _build_settings_menu()),
        pystray.MenuItem(t('menu.maintenance'), _build_maintenance_menu()),
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


def _build_maintenance_menu():
    scripts = app_paths.maintenance_scripts()
    items = [
        pystray.MenuItem(t("menu.check_update"), action_check_update),
        pystray.MenuItem(t("menu.apply_update"), action_apply_update),
        pystray.MenuItem(t("menu.update_source"), action_configure_update_source),
        pystray.MenuItem(t("menu.open_releases"), action_open_releases),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            t("menu.run_setup"),
            action_run_setup,
            visible=lambda item: scripts.get("setup") is not None,
        ),
        pystray.MenuItem(
            t("menu.run_update_bat"),
            action_run_update_bat,
            visible=lambda item: scripts.get("update") is not None,
        ),
        pystray.MenuItem(
            t("menu.run_uninstall"),
            action_run_uninstall,
            visible=lambda item: scripts.get("uninstall") is not None,
        ),
        pystray.MenuItem(t("menu.open_install_folder"), action_open_install_folder),
    ]
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
            (t('menu.interval_auto'), 0),
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

    cur_metric = user_settings.get("tray_icon_metric", "session")
    metric_items = [
        pystray.MenuItem(
            label,
            _make_set_tray_metric(value),
            checked=lambda item, v=value: v == cur_metric,
            radio=True,
        )
        for label, value in (
            (t("menu.metric_session"), "session"),
            (t("menu.metric_weekly"), "weekly"),
            (t("menu.metric_max"), "max"),
        )
    ]

    dw_enabled = bool((user_settings.get("desktop_widget") or {}).get("enabled"))

    return pystray.Menu(
        pystray.MenuItem(t('menu.alert_thresholds'),
                         pystray.Menu(*threshold_items)),
        pystray.MenuItem(
            t('menu.sound_alerts'),
            action_toggle_sound,
            checked=lambda item: bool(user_settings.get("sound_alerts", True)),
        ),
        pystray.MenuItem(
            t("menu.notify_on_update"),
            action_toggle_notify_on_update,
            checked=lambda item: bool(user_settings.get("notify_on_update", True)),
        ),
        pystray.MenuItem(t("menu.tray_metric"), pystray.Menu(*metric_items)),
        pystray.MenuItem(
            t("menu.desktop_widget_enable"),
            action_toggle_desktop_widget,
            visible=lambda item: desktop_widget.is_supported(),
            checked=lambda item: dw_enabled,
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


def _menu_opus_text() -> str:
    snap = state.snapshot
    if not snap or not snap.ok or snap.opus_pct is None:
        return ""
    pct = snap.opus_pct
    return (
        f"{color_emoji(pct)} {t('bar.opus_short')}  {unicode_bar(pct)}  {pct:>3}%  "
        f"· {t('bar.resets_in', time=format_reset(snap.opus_reset_seconds))}"
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

def _acquire_single_instance() -> bool:
    return app_platform.acquire_single_instance()


def _start_poller(icon: pystray.Icon) -> None:
    """pystray setup hook — show icon and start the background poll thread."""
    icon.visible = True
    _sync_desktop_widget(icon)
    threading.Thread(target=poll_loop, args=(icon,), daemon=True).start()


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
    if sys.platform == "win32":
        try:
            app_platform.set_app_identity(config.WIN_APP_USER_MODEL_ID)
        except Exception:
            pass

    _redirect_stderr_to_log()

    if not _acquire_single_instance():
        app_platform.already_running_message(config.APP_NAME)
        return

    try:
        user_settings.load()
        notifications.init(config.APP_NAME)

        while not state.stop.is_set():
            icon = pystray.Icon(
                config.APP_ID,
                icon=render_icon(None, theme=_current_theme(),
                                 style=_current_icon_style()),
                title=f"{config.APP_NAME}\nStarting…",
                menu=build_menu(),
            )

            icon.run(setup=_start_poller)

            if state.stop.is_set():
                break

            # pystray exited without Quit — usually a Win32/menu race; restart.
            try:
                sys.stderr.write(
                    f"=== tray loop exited unexpectedly "
                    f"{time.strftime('%Y-%m-%d %H:%M:%S')} — restarting in 3s ===\n"
                )
            except Exception:
                pass
            time.sleep(3)

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
