"""
Reads the Claude Code OAuth token from local storage.

OAuth discovery is implemented in auth_discovery.py (multi-source, per-OS order).
This module provides shared helpers and read_credentials() delegates there.

Typical order:
  1. Environment variables (CLAUDE_CODE_OAUTH_TOKEN, ANTHROPIC_AUTH_TOKEN)
  2. Claude Desktop (config.json oauth:tokenCache — Windows/macOS)
  3. OS secure storage (Windows Credential Manager / macOS Keychain)
  4. Claude Code credential files (~/.claude/.credentials.json, etc.)

Run: python src/token_reader.py --probe
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional


_TOKEN_KEYS = (
    "accessToken",
    "access_token",
    "oauth_token",
    "token",
    "bearerToken",
)

_PLAN_KEYS = ("subscriptionType", "subscription_type", "plan", "tier")
_RATE_TIER_KEYS = ("rateLimitTier", "rate_limit_tier")

_WIN_CRED_TARGETS = (
    "Claude Code-credentials",
    "Claude Code",
    "claude-code-credentials",
)


class TokenError(Exception):
    """Raised when the OAuth token cannot be read."""

    pass


def _claude_config_dir() -> Path:
    """User-level Claude config directory (~/.claude or CLAUDE_CONFIG_DIR)."""
    override = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude"


def _candidate_paths() -> list[Path]:
    """Credential file locations, most specific first."""
    home = Path.home()
    config_dir = _claude_config_dir()
    seen: set[Path] = set()
    candidates: list[Path] = []

    def _add(p: Path) -> None:
        resolved = p.expanduser()
        if resolved not in seen:
            seen.add(resolved)
            candidates.append(resolved)

    _add(config_dir / ".credentials.json")
    _add(home / ".claude" / ".credentials.json")
    _add(home / ".config" / "claude" / "credentials.json")
    _add(home / ".claude.json")

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            _add(Path(appdata) / "Claude" / "credentials.json")
            _add(Path(appdata) / "Claude" / ".credentials.json")

    return candidates


def find_credentials_path() -> Optional[Path]:
    """Return the first credentials file that exists and contains a token."""
    for path in _candidate_paths():
        if not path.is_file():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if _extract_token(data):
                return path
        except (OSError, json.JSONDecodeError):
            continue
    return None


def _extract_token(data) -> Optional[str]:
    """Recursively search a dict/list for a likely OAuth bearer token."""
    if isinstance(data, dict):
        for key in _TOKEN_KEYS:
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        for value in data.values():
            result = _extract_token(value)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _extract_token(item)
            if result:
                return result
    return None


def _find_first(data, keys: tuple[str, ...]) -> Optional[str]:
    if isinstance(data, dict):
        for k in keys:
            val = data.get(k)
            if isinstance(val, str) and val:
                return val
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
    if tier:
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


def _credentials_from_data(data: dict, source: str) -> dict:
    token = _extract_token(data)
    if not token:
        raise TokenError(f"No OAuth token in {source}")
    plan = _format_plan(
        _find_first(data, _PLAN_KEYS),
        _find_first(data, _RATE_TIER_KEYS),
    )
    return {"token": token, "plan": plan, "raw": data, "source": source}


def _read_env_token() -> Optional[dict]:
    for name in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN"):
        val = os.environ.get(name, "").strip()
        if val:
            return {
                "token": val,
                "plan": None,
                "raw": {"source": name},
                "source": f"env:{name}",
            }
    return None


def _read_windows_credential_manager() -> Optional[dict]:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None

    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        ]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    advapi32 = ctypes.windll.advapi32
    CRED_TYPE_GENERIC = 1

    user = os.environ.get("USERNAME", "")
    targets = list(_WIN_CRED_TARGETS)
    if user:
        targets.append(f"Claude Code-credentials:{user}")

    pcred = ctypes.POINTER(CREDENTIALW)()

    for target in targets:
        if not advapi32.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)):
            continue
        try:
            blob_size = int(pcred.contents.CredentialBlobSize)
            if blob_size <= 0 or not pcred.contents.CredentialBlob:
                continue
            blob = ctypes.string_at(pcred.contents.CredentialBlob, blob_size)
            text = blob.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # Some installs store the bearer token as plain text.
                if text.startswith("sk-ant-"):
                    return {
                        "token": text,
                        "plan": None,
                        "raw": {"source": "windows-credential-manager"},
                        "source": f"win-cred:{target}",
                    }
                continue
            return _credentials_from_data(data, f"win-cred:{target}")
        except TokenError:
            continue
        finally:
            advapi32.CredFree(pcred)

    return None


def _read_credentials_files() -> Optional[dict]:
    last_error: Optional[str] = None
    for path in _candidate_paths():
        if not path.is_file():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return _credentials_from_data(data, str(path))
        except json.JSONDecodeError as e:
            last_error = f"{path} is not valid JSON: {e}"
        except OSError as e:
            last_error = f"Could not read {path}: {e}"
        except TokenError:
            continue
    if last_error:
        raise TokenError(last_error)
    return None


def read_token() -> str:
    return read_credentials()["token"]


def read_credentials(exclude_tokens: Optional[set] = None) -> dict:
    """
    Return {"token": str, "plan": Optional[str], "raw": dict, "source": str}.

    Delegates to auth_discovery which tries every supported source for this OS.
    ``exclude_tokens`` skips token values already known to be invalid so
    discovery falls through to the next source.
    """
    from auth_discovery import read_credentials as discover

    return discover(exclude_tokens=exclude_tokens)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Claude Quota Tray — auth probe")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Try each auth source and print status (for troubleshooting)",
    )
    args = parser.parse_args()

    if args.probe:
        from auth_discovery import probe_auth_sources

        print(f"Platform: {sys.platform}\n")
        for row in probe_auth_sources():
            mark = "OK " if row.ok else "FAIL"
            print(f"  [{mark}] {row.name}: {row.detail}")
        sys.exit(0)

    try:
        creds = read_credentials()
        src = creds.get("source", "?")
        token = creds["token"]
        print(f"Source: {src}")
        print(f"Token: {token[:8]}...{token[-4:]} (length {len(token)})")
        if creds.get("plan"):
            print(f"Plan: {creds['plan']}")
    except TokenError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
