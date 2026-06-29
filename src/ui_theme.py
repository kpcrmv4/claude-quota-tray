"""
Tk UI colour palettes aligned with tray icon theme (light / dark).
"""

from __future__ import annotations

from typing import TypedDict


class UiColors(TypedDict):
    BG: str
    PANEL_BG: str
    TRACK_BG: str
    TEXT: str
    MUTED: str
    BTN_BG: str
    BTN_BG_ACTIVE: str
    ACCENT: str


_DARK: UiColors = {
    "BG": "#1e1e1e",
    "PANEL_BG": "#262626",
    "TRACK_BG": "#2d2d2d",
    "TEXT": "#f5f5f5",
    "MUTED": "#94a3b8",
    "BTN_BG": "#2d2d2d",
    "BTN_BG_ACTIVE": "#3a3a3a",
    "ACCENT": "#60a5fa",
}

_LIGHT: UiColors = {
    "BG": "#f4f4f5",
    "PANEL_BG": "#ffffff",
    "TRACK_BG": "#e4e4e7",
    "TEXT": "#18181b",
    "MUTED": "#71717a",
    "BTN_BG": "#e4e4e7",
    "BTN_BG_ACTIVE": "#d4d4d8",
    "ACCENT": "#2563eb",
}


def effective_ui_theme() -> str:
    try:
        import settings as user_settings
        import theme as theme_mod
        return theme_mod.effective_theme(user_settings.get("theme", "auto"))
    except Exception:
        return "dark"


def colors() -> UiColors:
    return _LIGHT if effective_ui_theme() == "light" else _DARK
