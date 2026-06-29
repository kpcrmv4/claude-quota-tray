"""
Reusable Tk progress-bar widget plus helpers used by both the compact
status popup and the full history window.

The bar is a thin rounded capsule whose fill colour shifts from green
through yellow/orange to red as utilisation rises.
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

from ui_theme import colors as _ui_colors


def _c():
    return _ui_colors()


# Re-exported for callers; refreshed via refresh_color_constants().
BG = "#1e1e1e"
PANEL_BG = "#262626"
TRACK_BG = "#2d2d2d"
TEXT = "#f5f5f5"
MUTED = "#94a3b8"
BTN_BG = "#2d2d2d"
BTN_BG_ACTIVE = "#3a3a3a"


def refresh_color_constants() -> None:
    """Sync module-level colour names with current UI theme."""
    global BG, PANEL_BG, TRACK_BG, TEXT, MUTED, BTN_BG, BTN_BG_ACTIVE
    c = _c()
    BG = c["BG"]
    PANEL_BG = c["PANEL_BG"]
    TRACK_BG = c["TRACK_BG"]
    TEXT = c["TEXT"]
    MUTED = c["MUTED"]
    BTN_BG = c["BTN_BG"]
    BTN_BG_ACTIVE = c["BTN_BG_ACTIVE"]


refresh_color_constants()


# --- Font selection ------------------------------------------------------

_FAMILY_CACHE: dict[str, str] = {}

# Preferred family chains. First installed wins. Noto Sans Thai is preferred
# for Thai rendering since it ships with Google Fonts CDN and many systems
# have it; Leelawadee UI is the Windows 8+ fallback; Segoe UI is the last
# resort and renders Thai acceptably on modern Windows.
_THAI_FAMILY_CHAIN = (
    "Noto Sans Thai",
    "Noto Sans Thai UI",
    "Leelawadee UI",
    "Sarabun",
    "Segoe UI",
)
_DEFAULT_FAMILY_CHAIN = (
    "Segoe UI",
    "Helvetica",
    "TkDefaultFont",
)


def _resolve_family(chain: tuple[str, ...]) -> str:
    """Return the first installed family from the chain, cached."""
    key = "|".join(chain)
    if key in _FAMILY_CACHE:
        return _FAMILY_CACHE[key]
    try:
        import tkinter.font as tkfont
        installed = set(tkfont.families())
    except Exception:
        installed = set()
    for family in chain:
        if family in installed or family.startswith("Tk"):
            _FAMILY_CACHE[key] = family
            return family
    _FAMILY_CACHE[key] = chain[-1]
    return chain[-1]


def ui_font(size: int, weight: str = "normal") -> tuple:
    """Pick a Tk font tuple, using Thai-friendly families when Thai is active."""
    try:
        from i18n import current_language
        lang = current_language()
    except Exception:
        lang = "en"
    chain = _THAI_FAMILY_CHAIN if lang == "th" else _DEFAULT_FAMILY_CHAIN
    return (_resolve_family(chain), size, weight)


def bar_color(pct: int) -> str:
    """Return the fill colour for a given utilisation percentage."""
    if pct < 50:
        return "#22c55e"   # green
    if pct < 75:
        return "#facc15"   # yellow
    if pct < 90:
        return "#f97316"   # orange
    return "#ef4444"       # red


def color_emoji(pct: Optional[int]) -> str:
    """Coloured-dot emoji corresponding to the bar colour. For menu labels."""
    if pct is None:
        return "⚪"
    if pct < 50:
        return "🟢"
    if pct < 75:
        return "🟡"
    if pct < 90:
        return "🟠"
    return "🔴"


def unicode_bar(pct: Optional[int], width: int = 10) -> str:
    """ASCII-art progress bar suitable for native menu labels."""
    if pct is None:
        return "░" * width
    pct = max(0, min(100, int(pct)))
    filled = int(round((pct / 100.0) * width))
    return ("█" * filled) + ("░" * (width - filled))


def _lighten(hex_color: str, amount: float) -> str:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    r = min(255, int(r + (255 - r) * amount))
    g = min(255, int(g + (255 - g) * amount))
    b = min(255, int(b + (255 - b) * amount))
    return f"#{r:02x}{g:02x}{b:02x}"


def rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius, **kwargs):
    """Public alias for chart panels and bars."""
    return _rounded_rect(canvas, x1, y1, x2, y2, radius, **kwargs)


def _rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius, **kwargs):
    r = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def paint_bar(canvas: tk.Canvas, pct: Optional[int]) -> None:
    """Paint the bar's track and fill on a canvas."""
    c = _c()
    canvas.delete("all")
    w = canvas.winfo_width()
    h = canvas.winfo_height()
    if w < 4 or h < 4:
        return

    _rounded_rect(canvas, 0, 0, w, h, radius=h / 2, fill=c["TRACK_BG"], outline="")
    if pct is None or pct <= 0:
        return

    fill_w = max(int(round((min(pct, 100) / 100.0) * w)), int(h))
    color = bar_color(pct)
    _rounded_rect(canvas, 0, 0, fill_w, h, radius=h / 2, fill=color, outline="")

    if fill_w > h:
        canvas.create_rectangle(
            int(h / 2), 2, fill_w - int(h / 2), int(h / 2),
            fill=_lighten(color, 0.18), outline="",
        )


def build_compact_bar(parent, label_text: str) -> dict:
    """Smaller bar for desktop widget (label + thin track only)."""
    c = _c()
    frame = tk.Frame(parent, bg=c["BG"])
    row = tk.Frame(frame, bg=c["BG"])
    row.pack(fill="x")
    tk.Label(
        row, text=label_text, font=ui_font(8),
        fg=c["MUTED"], bg=c["BG"], width=8, anchor="w",
    ).pack(side="left")
    pct_lbl = tk.Label(
        row, text="—", font=ui_font(9, "bold"),
        fg=c["TEXT"], bg=c["BG"], anchor="e",
    )
    pct_lbl.pack(side="right")
    canvas = tk.Canvas(frame, height=10, bg=c["BG"], highlightthickness=0, bd=0)
    canvas.pack(fill="x", pady=(2, 0))
    state = {"frame": frame, "canvas": canvas, "pct": pct_lbl, "value": None}

    def _redraw(_e=None):
        paint_bar(canvas, state["value"])

    canvas.bind("<Configure>", _redraw)
    state["redraw"] = _redraw
    return state


def apply_compact_bar(bar: dict, pct: Optional[int]) -> None:
    c = _c()
    bar["value"] = pct
    if pct is None:
        bar["pct"].configure(text="—", fg=c["MUTED"])
    else:
        bar["pct"].configure(text=f"{pct}%", fg=bar_color(pct))
    bar["redraw"]()


def build_bar(parent, label_text: str) -> dict:
    """Create one labelled progress bar and return its widget refs."""
    c = _c()
    frame = tk.Frame(parent, bg=c["PANEL_BG"])

    top = tk.Frame(frame, bg=c["PANEL_BG"])
    top.pack(fill="x", padx=14, pady=(10, 4))

    tk.Label(
        top, text=label_text, font=ui_font(10, "bold"),
        fg=c["TEXT"], bg=c["PANEL_BG"],
    ).pack(side="left")

    pct_w = tk.Label(
        top, text="—", font=ui_font(22, "bold"),
        fg=c["TEXT"], bg=c["PANEL_BG"],
    )
    pct_w.pack(side="right")

    canvas = tk.Canvas(frame, height=18, bg=c["PANEL_BG"],
                       highlightthickness=0, bd=0)
    canvas.pack(fill="x", padx=14)

    reset_w = tk.Label(
        frame, text="—", font=ui_font(9),
        fg=c["MUTED"], bg=c["PANEL_BG"], anchor="w",
    )
    reset_w.pack(fill="x", padx=14, pady=(4, 10))

    state = {
        "frame": frame, "canvas": canvas,
        "pct": pct_w, "reset": reset_w,
        "value": None,
    }

    def _redraw(_event=None):
        paint_bar(canvas, state["value"])

    canvas.bind("<Configure>", _redraw)
    state["redraw"] = _redraw
    return state


def apply_bar(bar: dict, pct: Optional[int], reset_seconds: Optional[int]) -> None:
    from i18n import t
    bar["value"] = pct
    if pct is None:
        bar["pct"].configure(text="—", fg=MUTED)
        bar["reset"].configure(text=t('bar.no_data'))
    else:
        bar["pct"].configure(text=f"{pct}%", fg=bar_color(pct))
        if reset_seconds is None:
            bar["reset"].configure(text=t('bar.resets_unknown'))
        else:
            bar["reset"].configure(
                text=t('bar.resets_in', time=fmt_seconds(reset_seconds))
            )
    bar["redraw"]()


def fmt_seconds(seconds: Optional[int]) -> str:
    if seconds is None:
        return "—"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m" if m else f"{h}h"
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    return f"{d}d {h}h" if h else f"{d}d"


def format_burn(burn: dict) -> str:
    from i18n import t
    lines = []
    for key, label_key in (("session", "bar.session_short"),
                           ("weekly", "bar.weekly_short")):
        info = (burn or {}).get(key, {}) or {}
        rate = info.get("rate")
        eta = info.get("eta_seconds")
        if rate is None:
            continue
        label = t(label_key)
        if eta is not None:
            lines.append(
                t('bar.burn_full_in', label=label, rate=rate,
                  eta=fmt_seconds(eta))
            )
        else:
            lines.append(t('bar.burn_no_eta', label=label, rate=rate))
    return "\n".join(lines) if lines else t('bar.burn_collecting')
