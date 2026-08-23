"""
Application configuration.

Values can be overridden via environment variables, useful for development
or for users who want to tweak behaviour without rebuilding.
"""

import os


# Poll interval in seconds. The API call costs almost nothing, but there is
# no point polling more than every ~30 seconds — Anthropic's headers don't
# change that frequently in practice.
POLL_INTERVAL_SECONDS = int(os.environ.get("CQT_POLL_INTERVAL", "60"))

# Initial poll delay (so the tray comes up fast, then fetches).
INITIAL_DELAY_SECONDS = 2

# Notification thresholds (only fire once per crossing, then reset on recovery).
NOTIFY_THRESHOLDS = [80, 95]

# Model to use for the throwaway API call (1 token, cheapest Haiku).
MODEL = os.environ.get("CQT_MODEL", "claude-haiku-4-5")

# Application identity (used by pystray and Windows for the tray entry).
APP_NAME = "Claude Quota Tray"
APP_ID = "ClaudeQuotaTray"
APP_VERSION = "0.4.0"
