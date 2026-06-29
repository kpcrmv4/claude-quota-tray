"""
Always-on-top compact quota bar on the desktop (Windows primary).
"""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from typing import Callable, Optional

import settings as user_settings
from bar_widget import apply_compact_bar, build_compact_bar, refresh_color_constants, ui_font
from i18n import t
from ui_theme import colors

_window_lock = threading.Lock()
_widget: Optional[tk.Tk] = None
_refresh_cb: Optional[Callable[[], None]] = None

SnapshotFetcher = Callable[[], dict]
ClickHandler = Callable[[], None]


def is_supported() -> bool:
    return sys.platform == "win32"


def show(get_data: SnapshotFetcher, on_click: ClickHandler) -> None:
    if not is_supported():
        return
    with _window_lock:
        w = _widget
    if w is not None:
        # Already showing — just bring forward and repaint with latest data.
        # `_refresh_cb` is the bar-applying callback set in _run(); do NOT
        # reassign it here or _apply_data() would recurse into itself.
        try:
            w.after(0, _bring_to_front)
            if _refresh_cb is not None:
                w.after(0, _refresh_cb)
            return
        except tk.TclError:
            pass
    threading.Thread(target=_run, args=(get_data, on_click), daemon=True).start()


def hide() -> None:
    global _widget
    with _window_lock:
        w = _widget
        _widget = None
    if w is not None:
        try:
            w.after(0, w.destroy)
        except tk.TclError:
            pass


def refresh(get_data: SnapshotFetcher) -> None:
    # Grab a local reference under the lock: hide() may null _widget out from
    # under us between the check and the .after() call (poll thread vs UI).
    with _window_lock:
        w = _widget
    if w is None or _refresh_cb is None:
        return
    try:
        w.after(0, _refresh_cb)
    except (tk.TclError, RuntimeError):
        pass


def _bring_to_front() -> None:
    if _widget is None:
        return
    try:
        _widget.deiconify()
        _widget.lift()
        _widget.attributes("-topmost", True)
    except tk.TclError:
        pass


def _run(get_data: SnapshotFetcher, on_click: ClickHandler) -> None:
    global _widget
    refresh_color_constants()
    cfg = user_settings.get("desktop_widget") or {}
    c = colors()

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    opacity = float(cfg.get("opacity", 0.92))
    try:
        root.attributes("-alpha", max(0.5, min(1.0, opacity)))
    except tk.TclError:
        pass

    w, h = 300, 72
    x = cfg.get("x")
    y = cfg.get("y")
    if x is None or y is None:
        root.update_idletasks()
        sw = root.winfo_screenwidth()
        x = sw - w - 24
        y = 48
    root.geometry(f"{w}x{h}+{int(x)}+{int(y)}")
    root.configure(bg=c["BG"])

    frame = tk.Frame(root, bg=c["BG"], padx=10, pady=8)
    frame.pack(fill="both", expand=True)

    drag = {"x": 0, "y": 0}

    def _start_drag(e):
        drag["x"], drag["y"] = e.x, e.y

    def _drag(e):
        nx = root.winfo_x() + e.x - drag["x"]
        ny = root.winfo_y() + e.y - drag["y"]
        root.geometry(f"+{nx}+{ny}")

    def _end_drag(_e):
        user_settings.update(desktop_widget={
            **cfg,
            "x": root.winfo_x(),
            "y": root.winfo_y(),
        })

    for wgt in (root, frame):
        wgt.bind("<Button-1>", _start_drag)
        wgt.bind("<B1-Motion>", _drag)
        wgt.bind("<ButtonRelease-1>", _end_drag)

    close_btn = tk.Label(
        frame, text="×", font=ui_font(12, "bold"),
        fg=c["MUTED"], bg=c["BG"], cursor="hand2",
    )
    close_btn.place(relx=1.0, x=-4, y=-4, anchor="ne")
    close_btn.bind("<Button-1>", lambda _e: hide())

    session_bar = build_compact_bar(frame, t("bar.session_short"))
    session_bar["frame"].pack(fill="x", pady=(0, 4))
    weekly_bar = build_compact_bar(frame, t("bar.weekly_short"))
    weekly_bar["frame"].pack(fill="x")

    def _click(_e=None):
        on_click()

    frame.bind("<Double-Button-1>", _click)

    state = {"session": session_bar, "weekly": weekly_bar}

    def _apply():
        refresh_color_constants()
        data = get_data()
        apply_compact_bar(state["session"], data.get("session_pct"))
        apply_compact_bar(state["weekly"], data.get("weekly_pct"))

    global _widget, _refresh_cb
    with _window_lock:
        _widget = root
    _refresh_cb = _apply
    _apply()
    root.mainloop()
    with _window_lock:
        if _widget is root:
            _widget = None
