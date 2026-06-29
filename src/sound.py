"""
Cross-platform alert sound. Best-effort, silent on failure.
"""

from __future__ import annotations

import app_platform as plat


def play_alert() -> None:
    plat.play_alert()
