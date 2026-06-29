"""
User-editable settings persisted to ~/.claude-quota-tray/settings.json.

Separate from config.py (which holds environment-driven defaults). These
values can change at runtime via the tray menu and survive across restarts.
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any, Dict


SETTINGS_DIR = Path.home() / ".claude-quota-tray"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"

_lock = threading.RLock()
_cache: Dict[str, Any] | None = None


def _defaults() -> Dict[str, Any]:
    return {
        "accounts": [
            {
                "id": str(uuid.uuid4()),
                "name": "Default",
                "mode": "auto",  # "auto" | "file"
                "path": None,
            }
        ],
        "active_account_id": None,  # falls back to accounts[0]
        "thresholds": [80, 95],
        "thresholds_session": [80, 95],
        "thresholds_weekly": [80, 95],
        "tray_icon_metric": "session",  # session | weekly | max
        "alert_snooze_until": 0.0,
        "notify_on_update": True,
        "desktop_widget": {
            "enabled": False,
            "x": None,
            "y": None,
            "opacity": 0.92,
            "click_action": "status",
        },
        "sound_alerts": True,
        "notify_before_reset": True,   # toast when a used-up limit is about to reset
        "reset_notice_minutes": 10,    # how early to fire that toast
        "schedule": {
            "enabled": False,
            "start_hour": 9,
            "end_hour": 18,
            "days": [0, 1, 2, 3, 4],  # Mon-Fri (0=Mon)
        },
        "theme": "auto",  # "auto" | "light" | "dark"
        "icon_style": "frame",  # "frame" | "solid" | "donut" | "bar"
        "poll_interval_seconds": 60,
        "history_retention_days": 7,
        "language": None,  # None → auto-detect from locale on first read
        # GitHub owner/repo (or URL) for release checks and source/.exe updates
        "update_github_repo": None,  # None → config.DEFAULT_UPDATE_REPO
    }


def _migrate(data: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in missing keys from defaults."""
    defaults = _defaults()
    for key, val in defaults.items():
        data.setdefault(key, val)
    sched = data.get("schedule") or {}
    for key, val in defaults["schedule"].items():
        sched.setdefault(key, val)
    data["schedule"] = sched

    if not data.get("accounts"):
        data["accounts"] = defaults["accounts"]
    if not data.get("active_account_id") and data.get("accounts"):
        data["active_account_id"] = data["accounts"][0]["id"]
    legacy = data.get("thresholds")
    if legacy and not data.get("thresholds_session"):
        data["thresholds_session"] = list(legacy)
    if legacy and not data.get("thresholds_weekly"):
        data["thresholds_weekly"] = list(legacy)
    dw = data.get("desktop_widget") or {}
    for key, val in defaults["desktop_widget"].items():
        dw.setdefault(key, val)
    data["desktop_widget"] = dw
    return data


def load() -> Dict[str, Any]:
    """Load settings from disk (cached). Creates the file on first run."""
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        if SETTINGS_PATH.exists():
            try:
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data = _migrate(data)
            except (OSError, json.JSONDecodeError):
                data = _defaults()
        else:
            data = _defaults()
        _cache = data
        save(data)
        return _cache


def save(data: Dict[str, Any] | None = None) -> None:
    """Persist settings to disk."""
    global _cache
    with _lock:
        if data is None:
            data = _cache
        if data is None:
            return
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        tmp.replace(SETTINGS_PATH)
        _cache = data


def update(**kwargs: Any) -> Dict[str, Any]:
    """Shallow-update top-level keys and persist."""
    with _lock:
        data = load()
        for key, val in kwargs.items():
            data[key] = val
        save(data)
        return data


def get(key: str, default: Any = None) -> Any:
    return load().get(key, default)
