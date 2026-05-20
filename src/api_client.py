"""
Makes a minimal Anthropic Messages API call and extracts usage information
from the `anthropic-ratelimit-unified-*` response headers.

The request body is intentionally as small as possible — one token of the
cheapest available Haiku model — because we only care about the response
headers. The body still incurs a tiny cost, but in practice this is
fractions of a fraction of a cent per poll.
"""

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx


API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Cheapest, smallest model. The exact string can be updated as new Haikus ship.
DEFAULT_MODEL = "claude-haiku-4-5"


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
    status_code: Optional[int] = None  # HTTP status (None on network error)

    @property
    def has_data(self) -> bool:
        return self.session_pct is not None or self.weekly_pct is not None


class APIError(Exception):
    """Raised when the API call itself fails (network, auth, etc.)."""
    pass


def _pct_from_utilization(raw: Optional[str]) -> Optional[int]:
    """Convert e.g. '0.67' -> 67, or '67' -> 67. Returns None on parse failure."""
    if raw is None:
        return None
    try:
        val = float(raw)
    except ValueError:
        return None
    # If the value is between 0 and 1, treat as a fraction.
    if 0.0 <= val <= 1.0:
        return max(0, min(100, round(val * 100)))
    # Otherwise assume already a percentage.
    return max(0, min(100, round(val)))


def _seconds_until_reset(raw: Optional[str]) -> Optional[int]:
    """
    Parse a reset header value into seconds-from-now.

    Accepts:
      - ISO 8601 timestamps (most common from Anthropic)
      - Unix epoch seconds as a number
      - Plain integer seconds-from-now
    """
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None

    # Try ISO 8601
    try:
        # Handle 'Z' suffix that fromisoformat doesn't accept in older Pythons
        ts = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = dt - datetime.now(timezone.utc)
        return max(0, int(delta.total_seconds()))
    except (ValueError, TypeError):
        pass

    # Try numeric
    try:
        val = float(raw)
        now = time.time()
        # Heuristic: if the value is much larger than "now", it's an epoch timestamp;
        # otherwise it's relative seconds.
        if val > now / 2:
            return max(0, int(val - now))
        return max(0, int(val))
    except ValueError:
        return None


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

    # Even on 4xx/5xx, the headers we want may still be present, so try to read them.
    rh = resp.headers

    snapshot = UsageSnapshot(
        session_pct=_pct_from_utilization(
            rh.get("anthropic-ratelimit-unified-5h-utilization")
        ),
        session_reset_seconds=_seconds_until_reset(
            rh.get("anthropic-ratelimit-unified-5h-reset")
        ),
        session_status=rh.get("anthropic-ratelimit-unified-5h-status"),

        weekly_pct=_pct_from_utilization(
            rh.get("anthropic-ratelimit-unified-7d-utilization")
        ),
        weekly_reset_seconds=_seconds_until_reset(
            rh.get("anthropic-ratelimit-unified-7d-reset")
        ),
        weekly_status=rh.get("anthropic-ratelimit-unified-7d-status"),

        ok=resp.is_success or snapshot_has_headers(rh),
        fetched_at=time.time(),
        status_code=resp.status_code,
    )

    if not resp.is_success and not snapshot.has_data:
        # Surface a meaningful error
        try:
            body = resp.json()
            err_msg = body.get("error", {}).get("message", resp.text[:200])
        except Exception:
            err_msg = resp.text[:200] or f"HTTP {resp.status_code}"
        snapshot.ok = False
        snapshot.error = f"API error ({resp.status_code}): {err_msg}"

    return snapshot


def snapshot_has_headers(headers) -> bool:
    """True if at least one ratelimit header is present."""
    return any(
        k.startswith("anthropic-ratelimit-unified-") for k in headers.keys()
    )


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
