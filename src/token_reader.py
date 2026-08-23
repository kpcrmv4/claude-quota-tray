"""
Reads the Claude Code OAuth token from the local credentials file.

Cross-platform: looks in ~/.claude/.credentials.json on Linux/macOS,
and %USERPROFILE%\\.claude\\.credentials.json on Windows.

The file format is JSON. The token may be stored under a few possible keys
depending on Claude Code version; we try them in order.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional


# Candidate locations for the credentials file, in order of preference.
def _candidate_paths():
    home = Path.home()
    candidates = [
        home / ".claude" / ".credentials.json",
        home / ".config" / "claude" / "credentials.json",
    ]
    # On Windows, also check AppData/Roaming just in case
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Claude" / "credentials.json")
    return candidates


# Candidate keys inside the JSON file where the token might live.
_TOKEN_KEYS = [
    "accessToken",
    "access_token",
    "oauth_token",
    "token",
    "bearerToken",
]

# The Anthropic subscription OAuth token always starts with this. Third-party
# tokens that share the credentials file (Supabase MCP servers store
# "sbp_oauth_..." under mcpOAuth, etc.) do not — we must never send those to
# api.anthropic.com or it (correctly) 401s with "Invalid bearer token".
_ANTHROPIC_TOKEN_PREFIX = "sk-ant"

# Sub-trees that hold OTHER services' credentials. Skipped entirely when
# searching for the Claude token so a generic recursive scan can't grab one.
_FOREIGN_TOKEN_KEYS = {"mcpOAuth", "mcp_oauth", "mcpServers", "mcp_servers"}

# Where Claude Code actually stores the subscription token, checked first.
_CLAUDE_OAUTH_KEYS = ("claudeAiOauth", "claude_ai_oauth", "claudeAi", "oauth")


class TokenError(Exception):
    """Raised when the OAuth token cannot be read."""
    pass


def find_credentials_path() -> Optional[Path]:
    """Return the first existing credentials file path, or None."""
    for p in _candidate_paths():
        if p.exists():
            return p
    return None


def _scan_token(data, require_anthropic: bool):
    """Recursively search for a token value, skipping foreign-credential trees.

    When ``require_anthropic`` is True, only returns values that look like an
    Anthropic token (``sk-ant`` prefix); otherwise returns the first token-shaped
    string found. Either way the ``mcpOAuth`` sub-tree is never descended into,
    so a third-party ``sbp_oauth_...`` token can't be mistaken for ours.
    """
    if isinstance(data, dict):
        for key in _TOKEN_KEYS:
            val = data.get(key)
            if isinstance(val, str) and val:
                if not require_anthropic or val.startswith(_ANTHROPIC_TOKEN_PREFIX):
                    return val
        for key, value in data.items():
            if key in _FOREIGN_TOKEN_KEYS:
                continue
            result = _scan_token(value, require_anthropic)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _scan_token(item, require_anthropic)
            if result:
                return result
    return None


def _extract_token(data) -> Optional[str]:
    """Find the Claude subscription OAuth token in the credentials tree.

    Order of preference:
      1. The token inside the known ``claudeAiOauth`` object.
      2. Any ``sk-ant`` token anywhere (outside foreign-credential sub-trees).
      3. As a last resort, any token-shaped string (older/unknown formats that
         predate the multi-service credentials file).
    """
    if isinstance(data, dict):
        for key in _CLAUDE_OAUTH_KEYS:
            branch = data.get(key)
            hit = _scan_token(branch, require_anthropic=False)
            if hit:
                return hit
    return (
        _scan_token(data, require_anthropic=True)
        or _scan_token(data, require_anthropic=False)
    )


_PLAN_KEYS = ("subscriptionType", "subscription_type", "plan", "tier")
_RATE_TIER_KEYS = ("rateLimitTier", "rate_limit_tier")


def _find_first(data, keys: tuple[str, ...]):
    """Recursively find the first matching key in a dict/list tree."""
    if isinstance(data, dict):
        for k in keys:
            if k in data and isinstance(data[k], str) and data[k]:
                return data[k]
        for v in data.values():
            r = _find_first(v, keys)
            if r:
                return r
    elif isinstance(data, list):
        for item in data:
            r = _find_first(item, keys)
            if r:
                return r
    return None


def _format_plan(subscription: Optional[str], tier: Optional[str]) -> Optional[str]:
    """Make a short display string like 'Max 5x' or 'Pro'."""
    if tier:
        # Examples: default_claude_max_5x, default_claude_max_20x, default_claude_pro
        low = tier.lower()
        multiplier = ""
        for token in low.split("_"):
            if token.endswith("x") and token[:-1].isdigit():
                multiplier = " " + token
                break
        if "max" in low:
            return "Max" + multiplier
        if "pro" in low:
            return "Pro"
        if "team" in low:
            return "Team" + multiplier
    if subscription:
        return subscription[:1].upper() + subscription[1:]
    return None


def read_token() -> str:
    """Read the OAuth token from the credentials file."""
    return read_credentials()["token"]


def read_credentials() -> dict:
    """
    Read the credentials file and return a dict:
        {"token": str, "plan": Optional[str], "raw": dict}

    'plan' is a short display label like 'Max 5x' / 'Pro' / None.

    Raises TokenError if the file is missing, unparseable, or has no token.
    """
    path = find_credentials_path()
    if path is None:
        searched = "\n  - ".join(str(p) for p in _candidate_paths())
        raise TokenError(
            "Claude Code credentials file not found.\n"
            "Searched:\n  - " + searched + "\n\n"
            "Make sure Claude Code is installed and you have signed in at least once."
        )

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise TokenError(f"Credentials file at {path} is not valid JSON: {e}")
    except OSError as e:
        raise TokenError(f"Could not read credentials file at {path}: {e}")

    token = _extract_token(data)
    if not token:
        raise TokenError(
            f"Credentials file at {path} was read, but no recognisable "
            f"OAuth token field was found. Expected one of: {_TOKEN_KEYS}"
        )

    # Prefer plan/tier from the Claude branch; fall back to a whole-tree scan
    # for older formats. (mcpOAuth entries don't carry these keys, but anchoring
    # to the Claude branch keeps this correct if that ever changes.)
    plan_scope = data
    for key in _CLAUDE_OAUTH_KEYS:
        if isinstance(data, dict) and isinstance(data.get(key), dict):
            plan_scope = data[key]
            break
    plan = _format_plan(
        _find_first(plan_scope, _PLAN_KEYS) or _find_first(data, _PLAN_KEYS),
        _find_first(plan_scope, _RATE_TIER_KEYS) or _find_first(data, _RATE_TIER_KEYS),
    )
    return {"token": token, "plan": plan, "raw": data}


if __name__ == "__main__":
    # Manual test: print the path and a redacted preview of the token.
    try:
        path = find_credentials_path()
        print(f"Credentials file: {path}")
        token = read_token()
        print(f"Token: {token[:8]}...{token[-4:]} (length {len(token)})")
    except TokenError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
