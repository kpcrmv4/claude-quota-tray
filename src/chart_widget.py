"""
Reusable time-series chart panels for the history window (stdlib Tk only).
"""

from __future__ import annotations

import time
import tkinter as tk
from datetime import datetime
from typing import Optional

from bar_widget import MUTED, bar_color, rounded_rect, ui_font
from i18n import t
from ui_theme import colors


def build_chart_panel(parent: tk.Widget, title_text: str) -> dict:
    c = colors()
    frame = tk.Frame(parent, bg=c["PANEL_BG"])
    head = tk.Frame(frame, bg=c["PANEL_BG"])
    head.pack(fill="x", padx=12, pady=(8, 4))
    title_lbl = tk.Label(
        head, text=title_text, font=ui_font(10, "bold"),
        fg=c["TEXT"], bg=c["PANEL_BG"],
    )
    title_lbl.pack(side="left")
    canvas = tk.Canvas(
        frame, height=168, bg=c["PANEL_BG"],
        highlightthickness=0, bd=0,
    )
    canvas.pack(fill="x", padx=10, pady=(0, 10))
    state: dict = {
        "frame": frame, "canvas": canvas, "title_lbl": title_lbl,
        "rows": [], "col_idx": 1, "hours": 24.0, "tooltip_id": None,
    }
    canvas.bind("<Motion>", lambda e: _show_hover_tooltip(canvas, state, e.x, e.y))
    canvas.bind("<Leave>", lambda _e: _hide_hover_tooltip(canvas, state))
    return state


def redraw_series(panel: dict, rows: list, col_idx: int, *, hours: float = 24) -> None:
    panel["rows"] = rows
    panel["col_idx"] = col_idx
    panel["hours"] = hours
    canvas = panel["canvas"]
    _hide_hover_tooltip(canvas, panel)
    canvas.delete("all")
    w, h = canvas.winfo_width(), canvas.winfo_height()
    if w < 50 or h < 50:
        return
    c = colors()
    pad_l, pad_r, pad_t, pad_b = 44, 12, 14, 28
    plot_w, plot_h = w - pad_l - pad_r, h - pad_t - pad_b
    if plot_w < 20 or plot_h < 20:
        return
    rounded_rect(
        canvas, pad_l, pad_t, pad_l + plot_w, pad_t + plot_h,
        radius=8, fill=c["TRACK_BG"], outline="",
    )
    for pct in (0, 25, 50, 75, 100):
        y = pad_t + plot_h - (pct / 100.0) * plot_h
        canvas.create_line(pad_l, y, pad_l + plot_w, y, fill=c["BTN_BG_ACTIVE"], width=1)
        canvas.create_text(pad_l - 6, y, text=f"{pct}%", anchor="e", fill=MUTED, font=ui_font(8))
    now = time.time()
    span = max(hours * 3600, 1)
    start = now - span
    for ts, label in _time_ticks(hours, now, start):
        x = pad_l + ((ts - start) / span) * plot_w
        canvas.create_text(x, pad_t + plot_h + 10, text=label, fill=MUTED, font=ui_font(8))
    series = [(r[0], r[col_idx]) for r in rows if r[col_idx] is not None]
    if not series:
        canvas.create_text(
            pad_l + plot_w / 2, pad_t + plot_h / 2,
            text=t("window.no_history"), fill=MUTED, font=ui_font(10),
        )
        return

    def to_xy(ts: float, pct: int) -> tuple[float, float]:
        return (
            pad_l + ((ts - start) / span) * plot_w,
            pad_t + plot_h - (pct / 100.0) * plot_h,
        )

    pts = [to_xy(ts, pct) for ts, pct in series]
    line_color = bar_color(series[-1][1])
    if len(pts) >= 2:
        flat_area = [pad_l, pad_t + plot_h]
        for x, y in pts:
            flat_area.extend([x, y])
        flat_area.extend([pts[-1][0], pad_t + plot_h])
        canvas.create_polygon(*flat_area, fill=_dim(line_color, 0.35), outline="")
        flat_line: list[float] = []
        for x, y in pts:
            flat_line.extend([x, y])
        canvas.create_line(*flat_line, fill=line_color, width=2, smooth=True)
    else:
        x, y = pts[0]
        canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill=line_color, outline="")
    lx, ly = pts[-1]
    canvas.create_oval(lx - 5, ly - 5, lx + 5, ly + 5, fill=line_color, outline=c["TEXT"], width=1)


def _time_ticks(hours: float, now: float, start: float) -> list[tuple[float, str]]:
    if hours <= 25:
        return [
            (now - ha * 3600, datetime.fromtimestamp(now - ha * 3600).strftime("%H:%M"))
            for ha in (24, 18, 12, 6, 0)
        ]
    out: list[tuple[float, str]] = []
    days = int(hours / 24)
    step = max(1, days // 6)
    for d in range(days, -1, -step):
        ts = now - d * 86400
        if ts >= start:
            out.append((ts, datetime.fromtimestamp(ts).strftime("%m/%d")))
    if not out:
        out.append((now, datetime.fromtimestamp(now).strftime("%m/%d")))
    return out


def _dim(hex_color: str, factor: float) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}"


def _show_hover_tooltip(canvas: tk.Canvas, panel: dict, mx: int, my: int) -> None:
    rows, col, hours = panel.get("rows") or [], panel.get("col_idx", 1), panel.get("hours", 24.0)
    if not rows:
        return
    now = time.time()
    span = max(hours * 3600, 1)
    start = now - span
    pad_l, plot_w = 44, canvas.winfo_width() - 44 - 12
    if plot_w < 20:
        return
    rel = (mx - pad_l) / plot_w
    if rel < 0 or rel > 1:
        _hide_hover_tooltip(canvas, panel)
        return
    target_ts = start + rel * span
    best, best_dist = None, float("inf")
    for r in rows:
        if r[col] is None:
            continue
        d = abs(r[0] - target_ts)
        if d < best_dist:
            best_dist, best = d, r
    if best is None or best_dist > span * 0.08:
        _hide_hover_tooltip(canvas, panel)
        return
    text = t("window.chart_hover", time=datetime.fromtimestamp(best[0]).strftime("%Y-%m-%d %H:%M"), pct=best[col])
    _hide_hover_tooltip(canvas, panel)
    c = colors()
    panel["tooltip_id"] = canvas.create_text(mx, max(12, my - 14), text=text, anchor="s", fill=c["TEXT"], font=ui_font(9), tags=("tooltip",))
    bbox = canvas.bbox(panel["tooltip_id"])
    if bbox:
        canvas.create_rectangle(bbox[0] - 4, bbox[1] - 2, bbox[2] + 4, bbox[3] + 2, fill=c["PANEL_BG"], outline=c["ACCENT"], tags=("tooltip_bg",))
        canvas.tag_raise(panel["tooltip_id"])


def _hide_hover_tooltip(canvas: tk.Canvas, panel: dict) -> None:
    canvas.delete("tooltip")
    canvas.delete("tooltip_bg")
    panel["tooltip_id"] = None
