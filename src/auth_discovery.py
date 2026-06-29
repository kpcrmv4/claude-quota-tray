"""
Unified OAuth discovery for Claude Quota Tray.

Tries multiple sources in platform-aware order so the app works whether the
user signs in via Claude Desktop, Claude Code CLI, or a manual env var.

Each provider returns None on "not applicable / not found" and raises
TokenError only for unexpected failures worth surfacing.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from token_reader import (
    TokenError,
    _credentials_from_data,
    _format_plan,
    _read_credentials_files,
    _read_env_token,
    _read_windows_credential_manager,
)


@dataclass(frozen=True)
class AuthProbeResult:
    name: str
    ok: bool
    detail: str


Provider = Callable[[], Optional[dict]]


def _try_desktop() -> Optional[dict]:
    from desktop_auth import try_read_desktop_credentials

    return try_read_desktop_credentials()


def _try_macos_keychain() -> Optional[dict]:
    if sys.platform != "darwin":
        return None
    import subprocess

    for service in ("Claude Code-credentials", "Claude Code"):
        try:
            proc = subprocess.run(
                ["security", "find-generic-password", "-s", service, "-w"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                continue
            text = proc.stdout.strip()
            if text.startswith("{"):
                return _credentials_from_data(
                    json.loads(text), f"mac-keychain:{service}"
                )
            if text.startswith("sk-ant-"):
                return {
                    "token": text,
                    "plan": None,
                    "raw": {"service": service},
                    "source": f"mac-keychain:{service}",
                }
        except (OSError, json.JSONDecodeError, subprocess.SubprocessError, TokenError):
            continue
    return None


def _providers_for_platform() -> list[tuple[str, Provider]]:
    """(label, callable) in try order — first success wins."""
    chain: list[tuple[str, Provider]] = [
        ("environment", _read_env_token),
        ("claude-desktop", _try_desktop),
    ]
    if sys.platform == "win32":
        chain.append(("windows-credential-manager", _read_windows_credential_manager))
    elif sys.platform == "darwin":
        chain.append(("macos-keychain", _try_macos_keychain))
    chain.append(("credential-files", _read_credentials_files))
    return chain


def read_credentials(exclude_tokens: Optional[set] = None) -> dict:
    """
    Return {"token", "plan", "raw", "source"} from the first working provider.

    ``exclude_tokens`` lets the caller skip token values already known to be
    invalid (e.g. a source whose token returned 401), so discovery falls
    through to the next source instead of getting stuck on a stale token.

    Raises TokenError with a summary of everything that was tried.
    """
    exclude = exclude_tokens or set()
    failures: list[str] = []
    skipped_bad = False
    for name, provider in _providers_for_platform():
        try:
            creds = provider()
            if creds and creds.get("token"):
                if creds["token"] in exclude:
                    skipped_bad = True
                    failures.append(f"{name}: token rejected earlier (skipped)")
                    continue
                creds.setdefault("source", name)
                return creds
            failures.append(f"{name}: not found")
        except TokenError as e:
            failures.append(f"{name}: {e}")
        except Exception as e:
            failures.append(f"{name}: {type(e).__name__}: {e}")

    summary = _format_failure_summary(failures)
    if skipped_bad:
        summary = (
            "All discovered tokens were rejected (expired or invalid). "
            "Sign in again to Claude Desktop or Claude Code.\n\n" + summary
        )
    raise TokenError(summary)


def _token_fingerprint(token: str) -> str:
    token = token.strip()
    if len(token) <= 12:
        return f"len={len(token)}"
    return f"{token[:6]}...{token[-4:]} (len {len(token)})"


def _expiry_note(creds: dict) -> str:
    """Human note about token expiry, if the source exposes it."""
    raw = creds.get("raw") or {}
    expires_ms = None
    for key in ("expiresAt", "expires_at", "expiry"):
        val = raw.get(key) if isinstance(raw, dict) else None
        if isinstance(val, (int, float)):
            expires_ms = float(val)
            break
    if expires_ms is None:
        return ""
    secs = expires_ms / 1000.0 - time.time()
    if secs <= 0:
        return ", EXPIRED"
    if secs < 3600:
        return f", expires in {int(secs // 60)}m"
    if secs < 86400:
        return f", expires in {int(secs // 3600)}h"
    return f", expires in {int(secs // 86400)}d"


def probe_auth_sources() -> list[AuthProbeResult]:
    """Try every provider independently (for diagnostics on a new machine).

    Reports, per source: whether anything was found, the resolved sub-source,
    a token fingerprint (so two sources sharing one token are obvious),
    the detected plan, and expiry status when available.
    """
    results: list[AuthProbeResult] = []
    for name, provider in _providers_for_platform():
        try:
            creds = provider()
            if creds and creds.get("token"):
                src = creds.get("source", name)
                plan = creds.get("plan") or "-"
                fp = _token_fingerprint(creds["token"])
                detail = f"OK | {src} | {fp} | plan={plan}{_expiry_note(creds)}"
                results.append(AuthProbeResult(name, True, detail))
            else:
                results.append(AuthProbeResult(name, False, "not found / not applicable"))
        except TokenError as e:
            results.append(AuthProbeResult(name, False, str(e)[:200]))
        except Exception as e:
            results.append(AuthProbeResult(name, False, f"{type(e).__name__}: {e}"[:200]))
    return results


def _format_failure_summary(failures: list[str]) -> str:
    platform = sys.platform
    lines = "\n  - ".join(failures)
    hints = {
        "win32": (
            "On Windows: sign in to Claude Desktop (MSIX app) or Claude Code CLI. "
            "Paths include %LOCALAPPDATA%\\Packages\\Claude_*\\...\\Claude\\config.json "
            "and Credential Manager."
        ),
        "darwin": (
            "On macOS: sign in to Claude Desktop or Claude Code. "
            "Tokens may be in ~/Library/Application Support/Claude/ or Keychain."
        ),
        "linux": (
            "On Linux: sign in to Claude Desktop or Claude Code. "
            "Look for ~/.config/Claude/ or ~/.claude/.credentials.json."
        ),
    }.get(platform, "Sign in to Claude Desktop or Claude Code.")

    return (
        f"Claude OAuth token not found (platform={platform}).\n"
        f"Tried:\n  - {lines}\n\n"
        f"{hints}\n\n"
        "Override: set CLAUDE_CODE_OAUTH_TOKEN or Account → Manage accounts → "
        "pick a credentials file.\n"
        "Diagnostics: python src/token_reader.py --probe"
    )
