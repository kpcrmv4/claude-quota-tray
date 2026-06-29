"""
Makes a minimal Anthropic Messages API call and extracts usage information
from the `anthropic-ratelimit-unified-*` response headers.

The request body is intentionally as small as possible — one token of the
cheapest available Haiku model — because we only care about the response
headers. The body still incurs a tiny cost, but in practice this is
fractions of a fraction of a cent per poll.

Header format (subscription / OAuth "unified" rate limits, as used by Claude
Code and Claude Pro/Max — distinct from the developer-API tier headers):

  anthropic-ratelimit-unified-5h-utilization     fraction 0.0–1.0  (e.g. "0.0184")
  anthropic-ratelimit-unified-5h-reset           Unix epoch seconds (e.g. "1764554400")
  anthropic-ratelimit-unified-5h-status          status string ("allowed", …)
  anthropic-ratelimit-unified-7d-utilization     weekly fraction 0.0–1.0
  anthropic-ratelimit-unified-7d-reset / -status
  anthropic-ratelimit-unified-7d_oauth_opus-…    separate Opus weekly limit (Max)

The "-utilization" headers report a FRACTION in [0, 1], NOT a percentage
0–100 (confirmed against observed Claude Code / Max responses). We therefore
treat any value in [0, 1] as a fraction; values above 1 are interpreted
defensively as an already-expressed percentage so the app degrades sanely if
the format ever changes. The exact window segment for the Opus weekly limit
is discovered dynamically rather than hard-coded, so a server-side rename
does not silently drop it.
"""

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx


API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Cheapest, smallest model. The exact string can be updated as new Haikus ship.
DEFAULT_MODEL = "claude-haiku-4-5"

# Any Unix timestamp from this app's lifetime is far larger than any plausible
# "relative seconds" reset (a weekly window is ~604800 s). 2020-01-01 is a safe
# splitter between "absolute epoch" and "relative duration".
_EPOCH_THRESHOLD = 1_577_836_800  # 2020-01-01T00:00:00Z

_UNIFIED_PREFIX = "anthropic-ratelimit-unified-"
_UNIFIED_UTIL_RE = re.compile(
    rf"^{re.escape(_UNIFIED_PREFIX)}(?P<window>.+)-utilization$"
)


@dataclass
class UsageSnapshot:
    """One reading of Claude usage limits."""
    # 5-hour rolling limit
    session_pct: Optional[int]              # 0-100
    session_reset_seconds: Optional[int]    # seconds until reset
    session_status: Optional[str]           # 'allowed', 'allowed_warning', etc.

    # 7-day weekly limit
    weekly_pct: Optional[int]
    weekly_reset_seconds: Optional[int]
    weekly_status: Optional[str]

    # Meta
    ok: bool
    error: Optional[str] = None
    fetched_at: float = 0.0
    http_status: Optional[int] = None

    # Separate weekly Opus limit (Max plans). None when the account/plan does
    # not expose it. Kept at the end of the dataclass so existing positional /
    # keyword construction stays backward compatible.
    opus_pct: Optional[int] = None
    opus_reset_seconds: Optional[int] = None
    opus_status: Optional[str] = None

    @property
    def has_data(self) -> bool:
        return (
            self.session_pct is not None
            or self.weekly_pct is not None
            or self.opus_pct is not None
        )


class APIError(Exception):
    """Raised when the API call itself fails (network, auth, etc.)."""
    pass


def _pct_from_utilization(raw: Optional[str]) -> Optional[int]:
    """Convert a unified ``-utilization`` header to an integer percent 0-100.

    The header is a FRACTION in [0, 1] (e.g. ``'0.0184'`` → 2, ``'1'`` → 100).
    Values above 1 are treated defensively as an already-expressed percentage,
    so the reading stays sane if Anthropic ever switches the encoding.

    Returns None on parse failure.
    """
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val != val:  # NaN guard
        return None
    if val < 0:
        return 0
    if val <= 1.0:
        # Fraction → percent. Round half-up so 0.005 → 1, not 0.
        return min(100, int(val * 100 + 0.5))
    # Defensive: looks like it is already a percentage.
    return min(100, int(val + 0.5))


def _seconds_until_reset(raw: Optional[str]) -> Optional[int]:
    """
    Parse a reset header value into seconds-from-now (never negative).

    Accepts, in priority order:
      - Unix epoch seconds as a number (the real unified-header format)
      - ISO 8601 / RFC 3339 timestamps (with or without 'Z')
      - Plain integer seconds-from-now (small values)
    """
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None

    # Numeric first — the unified headers send an absolute Unix timestamp.
    try:
        val = float(raw)
    except ValueError:
        val = None
    if val is not None:
        if val != val:  # NaN
            return None
        now = time.time()
        if val >= _EPOCH_THRESHOLD:
            return max(0, int(val - now))
        # Small number: treat as relative seconds-from-now.
        return max(0, int(val))

    # Fall back to ISO 8601 / RFC 3339.
    try:
        ts = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = dt - datetime.now(timezone.utc)
        return max(0, int(delta.total_seconds()))
    except (ValueError, TypeError):
        return None


def _parse_unified_windows(headers) -> dict:
    """Discover every unified rate-limit window present in the response.

    Returns ``{window: {"pct", "reset", "status"}}`` keyed by the window
    segment of the header name (e.g. ``"5h"``, ``"7d"``, ``"7d_oauth_opus"``).
    Discovering windows dynamically means a new or renamed limit (notably the
    Opus weekly limit) is captured automatically instead of being dropped.
    """
    windows: dict = {}
    for key in headers.keys():
        m = _UNIFIED_UTIL_RE.match(key.lower())
        if not m:
            continue
        window = m.group("window")
        base = f"{_UNIFIED_PREFIX}{window}"
        windows[window] = {
            "pct": _pct_from_utilization(headers.get(key)),
            "reset": _seconds_until_reset(headers.get(f"{base}-reset")),
            "status": headers.get(f"{base}-status"),
        }
    return windows


def _select_weekly(windows: dict) -> tuple[dict, Optional[dict]]:
    """Split the discovered windows into (weekly, opus-weekly).

    The plain 7-day window is the general weekly limit; any window whose name
    mentions "opus" is the separate Opus weekly cap that Max plans expose.
    """
    weekly = windows.get("7d")
    opus = None
    for name, data in windows.items():
        if "opus" in name:
            opus = data
            break
    if weekly is None:
        # Fall back to any non-opus 7-day-ish window.
        for name, data in windows.items():
            if "opus" in name:
                continue
            if name.startswith("7d") or name in ("weekly", "week"):
                weekly = data
                break
    return (weekly or {}), opus


def fetch_usage(token: str, model: str = DEFAULT_MODEL,
                timeout: float = 10.0) -> UsageSnapshot:
    """
    Make one minimal API call and return a UsageSnapshot.

    Network / auth errors are returned inside the snapshot (ok=False) rather
    than raised, so the tray loop can keep running and display the error in
    the tooltip.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "."}],
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(API_URL, headers=headers, json=payload)
    except httpx.RequestError as e:
        return UsageSnapshot(
            session_pct=None, session_reset_seconds=None, session_status=None,
            weekly_pct=None, weekly_reset_seconds=None, weekly_status=None,
            ok=False, error=f"Network error: {e}", fetched_at=time.time(),
        )

    return snapshot_from_headers(resp.headers, resp)


def snapshot_from_headers(rh, resp=None) -> UsageSnapshot:
    """Build a UsageSnapshot from response headers (+ optional httpx response).

    Split out from ``fetch_usage`` so the parsing is unit-testable without a
    live HTTP call. Even on 4xx/5xx the unified headers may still be present
    (e.g. a 429 still reports utilization), so we always try to read them.
    """
    windows = _parse_unified_windows(rh)
    session = windows.get("5h", {})
    weekly, opus = _select_weekly(windows)

    is_success = bool(resp.is_success) if resp is not None else True
    status_code = resp.status_code if resp is not None else None

    snapshot = UsageSnapshot(
        session_pct=session.get("pct"),
        session_reset_seconds=session.get("reset"),
        session_status=session.get("status"),

        weekly_pct=weekly.get("pct"),
        weekly_reset_seconds=weekly.get("reset"),
        weekly_status=weekly.get("status"),

        ok=is_success or snapshot_has_headers(rh),
        fetched_at=time.time(),
        http_status=status_code,

        opus_pct=(opus or {}).get("pct"),
        opus_reset_seconds=(opus or {}).get("reset"),
        opus_status=(opus or {}).get("status"),
    )

    if resp is not None and not is_success and not snapshot.has_data:
        # No usable headers — surface a meaningful error.
        try:
            body = resp.json()
            err_msg = body.get("error", {}).get("message", resp.text[:200])
        except Exception:
            err_msg = resp.text[:200] or f"HTTP {resp.status_code}"
        snapshot.ok = False
        snapshot.error = f"API error ({resp.status_code}): {err_msg}"

    return snapshot


def snapshot_has_headers(headers) -> bool:
    """True if at least one unified ratelimit header is present."""
    return any(k.lower().startswith(_UNIFIED_PREFIX) for k in headers.keys())


def format_reset(seconds: Optional[int]) -> str:
    """Render seconds-until-reset as a compact human string."""
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        m = seconds // 60
        return f"{m}m"
    if seconds < 86400:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m" if m else f"{h}h"
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    return f"{d}d {h}h" if h else f"{d}d"


if __name__ == "__main__":
    # Manual test
    import sys
    from token_reader import read_token, TokenError

    try:
        token = read_token()
    except TokenError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    snap = fetch_usage(token)
    print(f"ok: {snap.ok}")
    if snap.error:
        print(f"error: {snap.error}")
    print(f"session: {snap.session_pct}% (reset in {format_reset(snap.session_reset_seconds)})")
    print(f"weekly:  {snap.weekly_pct}% (reset in {format_reset(snap.weekly_reset_seconds)})")
    if snap.opus_pct is not None:
        print(f"opus:    {snap.opus_pct}% (reset in {format_reset(snap.opus_reset_seconds)})")
