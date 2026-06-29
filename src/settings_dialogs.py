"""
Tkinter dialogs for editing user settings that don't fit in a tray
sub-menu (accounts, custom thresholds, schedule). Each dialog is opened
on its own thread so the tray icon stays responsive.

A simple `on_saved` callback is invoked after each successful save so the
caller can refresh menus / force a poll.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, Optional

import accounts
import settings as user_settings
from bar_widget import ui_font
from i18n import t


_BG = "#1e1e1e"
_FG = "#f5f5f5"
_MUTED = "#94a3b8"
_ACCENT = "#60a5fa"
_BTN_BG = "#2d2d2d"
_BTN_BG_ACTIVE = "#3a3a3a"
_ENTRY_BG = "#262626"

_dialog_lock = threading.Lock()
_open_dialogs: dict[str, tk.Tk] = {}


def _spawn(kind: str, builder: Callable[[tk.Tk], None]) -> None:
    """Run a Tk dialog on its own thread and dedupe by kind."""
    with _dialog_lock:
        existing = _open_dialogs.get(kind)
        if existing is not None:
            try:
                existing.lift()
                existing.focus_force()
                return
            except tk.TclError:
                _open_dialogs.pop(kind, None)

    def _worker():
        root = tk.Tk()
        root.configure(bg=_BG)
        with _dialog_lock:
            _open_dialogs[kind] = root

        def _on_close():
            with _dialog_lock:
                _open_dialogs.pop(kind, None)
            try:
                root.destroy()
            except tk.TclError:
                pass

        root.protocol("WM_DELETE_WINDOW", _on_close)
        builder(root)
        root.mainloop()

    threading.Thread(target=_worker, daemon=True).start()


def _styled_button(parent, text, command, *, primary=False):
    bg = _ACCENT if primary else _BTN_BG
    fg = "#0b1220" if primary else _FG
    return tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, relief="flat", padx=14, pady=6,
        activebackground=_BTN_BG_ACTIVE, activeforeground=_FG,
        font=ui_font(9, "bold" if primary else "normal"),
        cursor="hand2",
    )


def _label(parent, text, *, muted=False, font=None):
    return tk.Label(
        parent, text=text,
        fg=_MUTED if muted else _FG, bg=_BG,
        font=font or ui_font(9),
    )


def _entry(parent, var):
    return tk.Entry(
        parent, textvariable=var,
        bg=_ENTRY_BG, fg=_FG, insertbackground=_FG,
        relief="flat", font=ui_font(10),
        highlightthickness=1, highlightcolor=_ACCENT,
        highlightbackground="#3a3a3a",
    )


# --- Accounts dialog ------------------------------------------------------

def open_accounts(on_saved: Callable[[], None]) -> None:
    _spawn("accounts", lambda root: _build_accounts(root, on_saved))


def _build_accounts(root: tk.Tk, on_saved: Callable[[], None]) -> None:
    root.title(t('dialog.accounts_title'))
    root.geometry("560x420")

    _label(root, t('dialog.accounts_heading'),
           font=ui_font(12, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
    _label(root, t('dialog.accounts_desc'),
           muted=True).pack(anchor="w", padx=16, pady=(0, 10))

    list_frame = tk.Frame(root, bg=_BG)
    list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

    listbox = tk.Listbox(
        list_frame,
        bg=_ENTRY_BG, fg=_FG,
        selectbackground=_ACCENT, selectforeground="#0b1220",
        relief="flat", highlightthickness=1, highlightcolor=_ACCENT,
        highlightbackground="#3a3a3a",
        font=ui_font(10), activestyle="none",
    )
    listbox.pack(side="left", fill="both", expand=True)

    scroll = tk.Scrollbar(list_frame, command=listbox.yview)
    scroll.pack(side="right", fill="y")
    listbox.config(yscrollcommand=scroll.set)

    def _refresh_list():
        listbox.delete(0, "end")
        for a in accounts.list_accounts():
            tag = "[auto]" if a.get("mode") == "auto" else f"[{a.get('path') or 'no path'}]"
            listbox.insert("end", f"  {a.get('name', '?')}   {tag}")

    _refresh_list()

    btn_row = tk.Frame(root, bg=_BG)
    btn_row.pack(fill="x", padx=16, pady=(0, 14))

    def _selected_account() -> Optional[dict]:
        sel = listbox.curselection()
        if not sel:
            return None
        idx = sel[0]
        items = accounts.list_accounts()
        if 0 <= idx < len(items):
            return items[idx]
        return None

    def _do_add():
        _open_add_account(root, _refresh_list, on_saved)

    def _do_remove():
        acct = _selected_account()
        if not acct:
            messagebox.showinfo(t('dialog.accounts_remove_title'),
                                t('dialog.accounts_no_selection'))
            return
        if len(accounts.list_accounts()) <= 1:
            messagebox.showwarning(t('dialog.accounts_remove_title'),
                                   t('dialog.accounts_keep_one'))
            return
        if not messagebox.askyesno(
                t('dialog.accounts_remove_title'),
                t('dialog.accounts_remove_confirm', name=acct.get('name'))):
            return
        accounts.remove_account(acct["id"])
        _refresh_list()
        on_saved()

    def _do_rename():
        acct = _selected_account()
        if not acct:
            messagebox.showinfo(t('dialog.accounts_rename'),
                                t('dialog.accounts_no_selection'))
            return
        new_name = _prompt_string(root, t('dialog.accounts_rename_title'),
                                  t('dialog.accounts_rename_label'),
                                  acct.get("name", ""))
        if not new_name:
            return
        data = user_settings.load()
        for a in data.get("accounts", []):
            if a["id"] == acct["id"]:
                a["name"] = new_name
        user_settings.save(data)
        _refresh_list()
        on_saved()

    _styled_button(btn_row, t('common.add'), _do_add,
                   primary=True).pack(side="left")
    _styled_button(btn_row, t('common.rename'), _do_rename).pack(
        side="left", padx=(8, 0))
    _styled_button(btn_row, t('common.remove'), _do_remove).pack(
        side="left", padx=(8, 0))
    _styled_button(btn_row, t('common.close'), root.destroy).pack(side="right")


def _open_add_account(parent: tk.Tk, on_added: Callable[[], None],
                      on_saved: Callable[[], None]) -> None:
    dlg = tk.Toplevel(parent)
    dlg.title(t('dialog.accounts_add_title'))
    dlg.configure(bg=_BG)
    dlg.geometry("520x260")
    dlg.transient(parent)
    dlg.grab_set()

    _label(dlg, t('dialog.accounts_field_name')).pack(
        anchor="w", padx=16, pady=(16, 4))
    name_var = tk.StringVar(value="Work")
    _entry(dlg, name_var).pack(fill="x", padx=16)

    _label(dlg, t('dialog.accounts_field_mode')).pack(
        anchor="w", padx=16, pady=(14, 4))
    mode_var = tk.StringVar(value="file")
    mode_row = tk.Frame(dlg, bg=_BG)
    mode_row.pack(fill="x", padx=16)
    for label, value in ((t('dialog.accounts_mode_auto'), "auto"),
                         (t('dialog.accounts_mode_file'), "file")):
        tk.Radiobutton(
            mode_row, text=label, variable=mode_var, value=value,
            bg=_BG, fg=_FG, selectcolor=_BG,
            activebackground=_BG, activeforeground=_FG,
            font=ui_font(9),
        ).pack(side="left", padx=(0, 16))

    _label(dlg, t('dialog.accounts_field_path')).pack(
        anchor="w", padx=16, pady=(14, 4))
    path_row = tk.Frame(dlg, bg=_BG)
    path_row.pack(fill="x", padx=16)
    path_var = tk.StringVar()
    path_entry = _entry(path_row, path_var)
    path_entry.pack(side="left", fill="x", expand=True)

    def _pick_file():
        p = filedialog.askopenfilename(
            parent=dlg, title=t('dialog.accounts_browse_title'),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if p:
            path_var.set(p)

    _styled_button(path_row, t('common.browse'), _pick_file).pack(
        side="left", padx=(8, 0))

    btn_row = tk.Frame(dlg, bg=_BG)
    btn_row.pack(fill="x", padx=16, pady=18, side="bottom")

    def _do_save():
        name = name_var.get().strip() or "Account"
        mode = mode_var.get()
        path = path_var.get().strip() or None
        if mode == "file" and not path:
            messagebox.showwarning(t('dialog.accounts_add_title'),
                                   t('dialog.accounts_missing_path'))
            return
        accounts.add_account(name, mode, path)
        on_added()
        on_saved()
        dlg.destroy()

    _styled_button(btn_row, t('common.save'), _do_save,
                   primary=True).pack(side="right")
    _styled_button(btn_row, t('common.cancel'), dlg.destroy).pack(
        side="right", padx=(0, 8))


def _prompt_string(parent: tk.Tk, title: str, label: str,
                   initial: str = "") -> Optional[str]:
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.configure(bg=_BG)
    dlg.geometry("360x150")
    dlg.transient(parent)
    dlg.grab_set()

    _label(dlg, label).pack(anchor="w", padx=16, pady=(16, 4))
    var = tk.StringVar(value=initial)
    entry = _entry(dlg, var)
    entry.pack(fill="x", padx=16)
    entry.focus_set()
    entry.select_range(0, "end")

    result: dict[str, Optional[str]] = {"value": None}

    def _ok():
        v = var.get().strip()
        result["value"] = v if v else None
        dlg.destroy()

    btn_row = tk.Frame(dlg, bg=_BG)
    btn_row.pack(fill="x", padx=16, pady=18, side="bottom")
    _styled_button(btn_row, t('common.ok'), _ok,
                   primary=True).pack(side="right")
    _styled_button(btn_row, t('common.cancel'), dlg.destroy).pack(
        side="right", padx=(0, 8))
    entry.bind("<Return>", lambda _e: _ok())

    parent.wait_window(dlg)
    return result["value"]


# --- Schedule dialog ------------------------------------------------------

_DAY_KEYS = ["day.mon", "day.tue", "day.wed", "day.thu",
             "day.fri", "day.sat", "day.sun"]


def open_schedule(on_saved: Callable[[], None]) -> None:
    _spawn("schedule", lambda root: _build_schedule(root, on_saved))


def _build_schedule(root: tk.Tk, on_saved: Callable[[], None]) -> None:
    root.title(t('dialog.schedule_title'))
    root.geometry("440x360")

    sched = dict(user_settings.get("schedule", {}) or {})

    _label(root, t('dialog.schedule_heading'),
           font=ui_font(12, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
    _label(root, t('dialog.schedule_desc'),
           muted=True).pack(anchor="w", padx=16, pady=(0, 12))

    enabled_var = tk.BooleanVar(value=bool(sched.get("enabled")))
    tk.Checkbutton(
        root, text=t('dialog.schedule_enable'),
        variable=enabled_var,
        bg=_BG, fg=_FG, selectcolor=_BG,
        activebackground=_BG, activeforeground=_FG,
        font=ui_font(10, "bold"),
    ).pack(anchor="w", padx=14)

    hours_row = tk.Frame(root, bg=_BG)
    hours_row.pack(fill="x", padx=16, pady=(14, 6))
    _label(hours_row, t('dialog.schedule_hours')).pack(side="left")

    start_var = tk.IntVar(value=int(sched.get("start_hour", 9)))
    end_var = tk.IntVar(value=int(sched.get("end_hour", 18)))

    start_spin = tk.Spinbox(
        hours_row, from_=0, to=23, width=4, textvariable=start_var,
        bg=_ENTRY_BG, fg=_FG, buttonbackground=_BTN_BG, relief="flat",
        font=ui_font(10),
    )
    start_spin.pack(side="left", padx=(8, 4))
    _label(hours_row, ":00  →").pack(side="left")
    end_spin = tk.Spinbox(
        hours_row, from_=0, to=24, width=4, textvariable=end_var,
        bg=_ENTRY_BG, fg=_FG, buttonbackground=_BTN_BG, relief="flat",
        font=ui_font(10),
    )
    end_spin.pack(side="left", padx=(8, 4))
    _label(hours_row, ":00").pack(side="left")

    _label(root, t('dialog.schedule_days'),
           muted=True).pack(anchor="w", padx=16, pady=(14, 4))
    days_row = tk.Frame(root, bg=_BG)
    days_row.pack(anchor="w", padx=12)
    day_vars: list[tk.BooleanVar] = []
    active_days = set(sched.get("days", [0, 1, 2, 3, 4]))
    for idx, key in enumerate(_DAY_KEYS):
        v = tk.BooleanVar(value=idx in active_days)
        day_vars.append(v)
        tk.Checkbutton(
            days_row, text=t(key), variable=v,
            bg=_BG, fg=_FG, selectcolor=_BG,
            activebackground=_BG, activeforeground=_FG,
            font=ui_font(9),
        ).pack(side="left", padx=2)

    btn_row = tk.Frame(root, bg=_BG)
    btn_row.pack(fill="x", padx=16, pady=18, side="bottom")

    def _do_save():
        days = [i for i, v in enumerate(day_vars) if v.get()]
        new = {
            "enabled": enabled_var.get(),
            "start_hour": int(start_var.get()),
            "end_hour": int(end_var.get()),
            "days": days or [0, 1, 2, 3, 4],
        }
        user_settings.update(schedule=new)
        on_saved()
        root.destroy()

    _styled_button(btn_row, t('common.save'), _do_save,
                   primary=True).pack(side="right")
    _styled_button(btn_row, t('common.cancel'), root.destroy).pack(
        side="right", padx=(0, 8))


# --- Thresholds dialog ----------------------------------------------------

def open_thresholds(on_saved: Callable[[], None]) -> None:
    _spawn("thresholds", lambda root: _build_thresholds(root, on_saved))


def _build_thresholds(root: tk.Tk, on_saved: Callable[[], None]) -> None:
    root.title(t('dialog.thresholds_title'))
    root.geometry("420x320")

    cur_s = user_settings.get("thresholds_session") or user_settings.get("thresholds", [80, 95])
    cur_w = user_settings.get("thresholds_weekly") or user_settings.get("thresholds", [80, 95])

    _label(root, t('dialog.thresholds_heading'),
           font=ui_font(12, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
    _label(root, t('dialog.thresholds_desc'),
           muted=True, font=ui_font(9)).pack(anchor="w", padx=16, pady=(0, 10))

    _label(root, t('bar.session_label'), font=ui_font(9, "bold")).pack(anchor="w", padx=16)
    var_s = tk.StringVar(value=", ".join(str(v) for v in cur_s))
    _entry(root, var_s).pack(fill="x", padx=16, pady=(2, 8))

    _label(root, t('bar.weekly_label'), font=ui_font(9, "bold")).pack(anchor="w", padx=16)
    var_w = tk.StringVar(value=", ".join(str(v) for v in cur_w))
    _entry(root, var_w).pack(fill="x", padx=16)

    sound_var = tk.BooleanVar(value=bool(user_settings.get("sound_alerts", True)))
    tk.Checkbutton(
        root, text=t('dialog.thresholds_play_sound'),
        variable=sound_var,
        bg=_BG, fg=_FG, selectcolor=_BG,
        activebackground=_BG, activeforeground=_FG,
        font=ui_font(9),
    ).pack(anchor="w", padx=14, pady=(14, 0))

    btn_row = tk.Frame(root, bg=_BG)
    btn_row.pack(fill="x", padx=16, pady=18, side="bottom")

    def _parse(raw: str) -> Optional[list[int]]:
        try:
            values = sorted({
                max(1, min(100, int(part.strip())))
                for part in raw.replace(";", ",").split(",") if part.strip()
            })
            return values if values else None
        except ValueError:
            return None

    def _do_save():
        sess = _parse(var_s.get())
        week = _parse(var_w.get())
        if sess is None or week is None:
            messagebox.showwarning(t('dialog.thresholds_heading'),
                                   t('dialog.thresholds_invalid'))
            return
        user_settings.update(
            thresholds=sess,
            thresholds_session=sess,
            thresholds_weekly=week,
            sound_alerts=sound_var.get(),
        )
        on_saved()
        root.destroy()

    _styled_button(btn_row, t('common.save'), _do_save,
                   primary=True).pack(side="right")
    _styled_button(btn_row, t('common.cancel'), root.destroy).pack(
        side="right", padx=(0, 8))


def open_update_source(on_saved: Optional[Callable[[], None]] = None) -> None:
    def _build(root: tk.Tk) -> None:
        import config

        cur = user_settings.get("update_github_repo") or config.DEFAULT_UPDATE_REPO

        root.title(t('dialog.update_source_title'))
        root.geometry("480x220")

        _label(root, t('dialog.update_source_heading'),
               font=ui_font(12, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
        _label(root, t('dialog.update_source_desc'),
               muted=True, font=ui_font(9)).pack(anchor="w", padx=16, pady=(0, 12))

        var = tk.StringVar(value=str(cur))
        _entry(root, var).pack(fill="x", padx=16)

        btn_row = tk.Frame(root, bg=_BG)
        btn_row.pack(fill="x", padx=16, pady=18, side="bottom")

        def _do_save():
            from updater import parse_github_repo

            raw = var.get().strip()
            try:
                parse_github_repo(raw)
            except ValueError:
                messagebox.showwarning(
                    t('dialog.update_source_heading'),
                    t('dialog.update_source_invalid'),
                )
                return
            user_settings.update(update_github_repo=raw)
            if on_saved:
                on_saved()
            root.destroy()

        _styled_button(btn_row, t('common.save'), _do_save,
                       primary=True).pack(side="right")
        _styled_button(btn_row, t('common.cancel'), root.destroy).pack(
            side="right", padx=(0, 8))

    _spawn("update_source", _build)


def confirm_apply_update(on_confirm: Callable[[], None]) -> None:
    def _build(root: tk.Tk) -> None:
        import config

        repo = user_settings.get("update_github_repo") or config.DEFAULT_UPDATE_REPO
        root.withdraw()
        ok = messagebox.askyesno(
            t('dialog.apply_update_title'),
            t('dialog.apply_update_confirm', repo=repo),
            parent=root,
        )
        root.destroy()
        if ok:
            on_confirm()

    _spawn("apply_update_confirm", _build)


def confirm_uninstall(on_confirm: Callable[[], None]) -> None:
    def _build(root: tk.Tk) -> None:
        root.withdraw()
        ok = messagebox.askyesno(
            t('menu.run_uninstall'),
            t('dialog.uninstall_confirm'),
            parent=root,
        )
        root.destroy()
        if ok:
            on_confirm()

    _spawn("uninstall_confirm", _build)
