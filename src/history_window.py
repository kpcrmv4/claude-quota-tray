"""
Full history window: progress bars + separate Session / Weekly chart panels.
"""

from __future__ import annotations

import csv
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, Optional

import chart_widget
import history
import settings as user_settings
from bar_widget import (
    apply_bar, build_bar, format_burn, refresh_color_constants, ui_font,
)
from i18n import t
from ui_theme import colors


_window_lock = threading.Lock()
_open_window: Optional[tk.Tk] = None

SnapshotFetcher = Callable[[], dict]


def show(account_id: str, account_name: str,
         get_data: Optional[SnapshotFetcher] = None,
         burn: Optional[dict] = None) -> None:
    with _window_lock:
        global _open_window
        if _open_window is not None:
            try:
                _open_window.lift()
                _open_window.focus_force()
                return
            except tk.TclError:
                _open_window = None

    if get_data is None:
        b = burn or {"session": {}, "weekly": {}}
        get_data = lambda: {
            "session_pct": None, "weekly_pct": None,
            "session_reset": None, "weekly_reset": None,
            "burn": b,
        }

    threading.Thread(
        target=_run_window,
        args=(account_id, account_name, get_data),
        daemon=True,
    ).start()


def _run_window(account_id: str, account_name: str,
                get_data: SnapshotFetcher) -> None:
    global _open_window
    refresh_color_constants()
    c = colors()

    root = tk.Tk()
    root.title(t("window.history_title", name=account_name))
    root.geometry("760x720")
    root.minsize(560, 520)
    root.configure(bg=c["BG"])

    with _window_lock:
        _open_window = root

    hours_var = tk.DoubleVar(value=24.0)

    header = tk.Frame(root, bg=c["BG"])
    header.pack(fill="x", padx=18, pady=(16, 0))
    title_box = tk.Frame(header, bg=c["BG"])
    title_box.pack(side="left")
    tk.Label(title_box, text=t("window.current_usage"), font=ui_font(13, "bold"), fg=c["TEXT"], bg=c["BG"]).pack(side="left")
    plan_lbl = tk.Label(title_box, text="", font=ui_font(10, "bold"), fg=c["ACCENT"], bg=c["BG"])
    plan_lbl.pack(side="left", padx=(10, 0))
    burn_lbl = tk.Label(header, text="", font=ui_font(10), fg=c["MUTED"], bg=c["BG"], justify="right")
    burn_lbl.pack(side="right")

    bars_panel = tk.Frame(root, bg=c["BG"])
    bars_panel.pack(fill="x", padx=18, pady=(10, 6))
    session_bar = build_bar(bars_panel, t("bar.session_label"))
    session_bar["frame"].pack(fill="x", pady=(0, 10))
    weekly_bar = build_bar(bars_panel, t("bar.weekly_label"))
    weekly_bar["frame"].pack(fill="x")

    range_row = tk.Frame(root, bg=c["BG"])
    range_row.pack(fill="x", padx=18, pady=(12, 4))
    tk.Label(range_row, text=t("window.history_range"), font=ui_font(11, "bold"), fg=c["TEXT"], bg=c["BG"]).pack(side="left")

    charts_box = tk.Frame(root, bg=c["BG"])
    charts_box.pack(fill="both", expand=True, padx=18, pady=(4, 4))
    session_chart = chart_widget.build_chart_panel(charts_box, t("bar.session_label"))
    session_chart["frame"].pack(fill="x", pady=(0, 8))
    weekly_chart = chart_widget.build_chart_panel(charts_box, t("bar.weekly_label"))
    weekly_chart["frame"].pack(fill="x")

    footer = tk.Frame(root, bg=c["BG"])
    footer.pack(fill="x", padx=18, pady=(0, 14))

    def _redraw_charts():
        hrs = hours_var.get()
        rows = history.recent(hrs, account_id)
        chart_widget.redraw_series(session_chart, rows, 1, hours=hrs)
        chart_widget.redraw_series(weekly_chart, rows, 2, hours=hrs)

    def _refresh_all():
        refresh_color_constants()
        data = get_data()
        apply_bar(session_bar, data.get("session_pct"), data.get("session_reset"))
        apply_bar(weekly_bar, data.get("weekly_pct"), data.get("weekly_reset"))
        burn_lbl.configure(text=format_burn(data.get("burn") or {}))
        plan = data.get("plan")
        plan_lbl.configure(text=("· " + plan) if plan else "")
        _redraw_charts()

    def _ensure_retention_for(hrs: float):
        # Longer views are only useful if history isn't pruned before it fills.
        # Bump retention upward (never down) so future data accumulates.
        try:
            need_days = int(hrs / 24)
            cur = int(user_settings.get("history_retention_days", 7))
            if need_days > cur:
                user_settings.update(history_retention_days=need_days + 1)
        except Exception:
            pass

    def _set_range(hrs: float):
        hours_var.set(hrs)
        _ensure_retention_for(hrs)
        _redraw_charts()

    for hrs, label_key in (
        (24, "window.range_24h"),
        (168, "window.range_7d"),
        (720, "window.range_30d"),
    ):
        tk.Radiobutton(
            range_row, text=t(label_key), variable=hours_var, value=hrs,
            command=lambda h=hrs: _set_range(h),
            bg=c["BG"], fg=c["TEXT"], selectcolor=c["BG"],
            activebackground=c["BG"], activeforeground=c["TEXT"],
            font=ui_font(9),
        ).pack(side="left", padx=(12, 0))

    def _export_csv():
        path = filedialog.asksaveasfilename(
            parent=root, defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All", "*.*")],
            initialfile=f"claude-quota-{account_name[:20]}.csv",
        )
        if not path:
            return
        try:
            history.export_csv(path, hours_var.get(), account_id)
            messagebox.showinfo(t("window.export_title"), t("window.export_ok", path=path), parent=root)
        except Exception as e:
            messagebox.showerror(t("window.export_title"), str(e), parent=root)

    tk.Button(footer, text=t("window.export_csv"), command=_export_csv,
              bg=c["BTN_BG"], fg=c["TEXT"], relief="flat",
              activebackground=c["BTN_BG_ACTIVE"], activeforeground=c["TEXT"],
              padx=12, pady=4, cursor="hand2").pack(side="left")
    tk.Button(footer, text=t("common.refresh"), command=_refresh_all,
              bg=c["BTN_BG"], fg=c["TEXT"], relief="flat",
              activebackground=c["BTN_BG_ACTIVE"], activeforeground=c["TEXT"],
              padx=14, pady=4, cursor="hand2").pack(side="right")

    session_chart["canvas"].bind("<Configure>", lambda _e: _redraw_charts())
    weekly_chart["canvas"].bind("<Configure>", lambda _e: _redraw_charts())
    root.after(50, _refresh_all)

    def _auto():
        try:
            _refresh_all()
        except tk.TclError:
            return
        root.after(30_000, _auto)

    root.after(30_000, _auto)

    def on_close():
        global _open_window
        with _window_lock:
            _open_window = None
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
