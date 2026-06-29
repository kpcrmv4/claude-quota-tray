"""
Read OAuth tokens from Claude Desktop (Electron) on Windows and macOS.

Claude Desktop stores tokens in config.json under ``oauth:tokenCache``,
encrypted with Chromium's v10 scheme (AES-256-GCM). The master key comes from:
  - Windows: DPAPI via Local State os_crypt.encrypted_key
  - macOS: Keychain "Claude Safe Storage" + PBKDF2 (same as Chromium on Mac)

Install paths differ by OS:
  Windows MSIX: %LOCALAPPDATA%\\Packages\\Claude_*\\LocalCache\\Roaming\\Claude\\
  Windows legacy: %APPDATA%\\Claude\\
  macOS: ~/Library/Application Support/Claude/
  Linux: ~/.config/Claude/ (encryption may vary; best-effort)
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from token_reader import TokenError, _format_plan


_CACHE_KEY = "oauth:tokenCache"
_KEYCHAIN_SERVICE_MAC = "Claude Safe Storage"


def claude_desktop_dirs() -> list[Path]:
    """Candidate Claude Desktop data directories, best match first."""
    dirs: list[Path] = []
    seen: set[Path] = set()
    home = Path.home()

    def _add(p: Path) -> None:
        resolved = p.expanduser()
        if resolved.is_dir() and resolved not in seen:
            seen.add(resolved)
            dirs.append(resolved)

    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            packages = Path(local) / "Packages"
            if packages.is_dir():
                for pkg in sorted(
                    packages.glob("Claude_*"),
                    key=lambda p: p.stat().st_mtime if p.is_dir() else 0,
                    reverse=True,
                ):
                    _add(pkg / "LocalCache" / "Roaming" / "Claude")
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            _add(Path(appdata) / "Claude")
    elif sys.platform == "darwin":
        _add(home / "Library" / "Application Support" / "Claude")
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        if xdg:
            _add(Path(xdg) / "Claude")
        _add(home / ".config" / "Claude")

    return dirs


def _require_crypto():
    try:
        from Crypto.Cipher import AES  # noqa: F401
    except ImportError as e:
        raise TokenError(
            "Claude Desktop decryption requires pycryptodome. "
            "Re-run Setup claude quota tray.bat (or pip install pycryptodome)."
        ) from e


def _decrypt_v10_payload(master_key: bytes, raw: bytes) -> bytes:
    _require_crypto()
    from Crypto.Cipher import AES

    if not raw.startswith(b"v10"):
        raise TokenError("Unexpected encryption format (expected v10 prefix)")
    iv = raw[3:15]
    payload = raw[15:]
    return AES.new(master_key, AES.MODE_GCM, nonce=iv).decrypt_and_verify(
        payload[:-16], payload[-16:]
    )


def _dpapi_decrypt(data: bytes) -> bytes:
    import ctypes
    import ctypes.wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    buf = ctypes.create_string_buffer(data)
    blob_in = DATA_BLOB(
        len(data),
        ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)),
    )
    blob_out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    ):
        raise OSError("DPAPI decryption failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _macos_chrome_derived_key() -> bytes:
    """PBKDF2 key used by Chromium on macOS (Claude Safe Storage)."""
    _require_crypto()
    from Crypto.Hash import SHA1
    from Crypto.Protocol.KDF import PBKDF2

    try:
        proc = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                _KEYCHAIN_SERVICE_MAC,
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise TokenError(f"macOS Keychain lookup failed: {e}") from e

    if proc.returncode != 0 or not proc.stdout.strip():
        raise TokenError(
            f"Keychain entry '{_KEYCHAIN_SERVICE_MAC}' not found — "
            "sign in to Claude Desktop first."
        )

    password = proc.stdout.strip().encode("utf-8")
    return PBKDF2(password, b"saltysalt", dkLen=16, count=1003, hmac_hash_module=SHA1)


def _chromium_master_key(claude_dir: Path) -> bytes:
    state_path = claude_dir / "Local State"
    if not state_path.is_file():
        raise TokenError(f"Local State not found: {state_path}")

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        enc_key_b64 = state["os_crypt"]["encrypted_key"]
    except (OSError, json.JSONDecodeError, KeyError) as e:
        raise TokenError(f"Could not read encryption key: {e}")

    enc_key = base64.b64decode(enc_key_b64)

    if sys.platform == "win32":
        if enc_key.startswith(b"DPAPI"):
            enc_key = enc_key[5:]
        return _dpapi_decrypt(enc_key)

    if sys.platform == "darwin":
        # Local State key is itself v10-encrypted with the Keychain-derived key.
        derived = _macos_chrome_derived_key()
        if enc_key.startswith(b"v10"):
            return _decrypt_v10_payload(derived, enc_key)
        raise TokenError("Unexpected macOS Local State key format")

    # Linux: OS key storage varies; credential files / env are more reliable.
    if enc_key.startswith(b"DPAPI"):
        raise TokenError(
            "Linux Claude Desktop uses OS key storage — use Claude Code "
            ".credentials.json or CLAUDE_CODE_OAUTH_TOKEN instead."
        )
    if enc_key.startswith(b"v10"):
        raise TokenError(
            "Linux encrypted token cache is not supported yet — use Claude Code "
            "CLI credentials or CLAUDE_CODE_OAUTH_TOKEN."
        )
    raise TokenError("Unsupported Claude Desktop encryption on this OS")


def _decrypt_token_cache(master_key: bytes, encrypted_b64: str) -> bytes:
    raw = base64.b64decode(encrypted_b64)
    return _decrypt_v10_payload(master_key, raw)


def _pick_cache_entry(cache: dict) -> dict:
    """Choose the best OAuth entry; prefer valid, claude_code-scoped tokens."""
    best: Optional[dict] = None
    best_score = -1.0
    now_ms = time.time() * 1000.0

    for key, entry in cache.items():
        if not isinstance(entry, dict):
            continue
        token = entry.get("token") or entry.get("accessToken")
        if not isinstance(token, str) or not token.strip():
            continue

        score = 0.0
        key_low = str(key).lower()
        if "claude_code" in key_low:
            score += 100.0
        if "api.anthropic.com" in key_low:
            score += 20.0
        if "user:inference" in key_low:
            score += 5.0

        expires = entry.get("expiresAt")
        if isinstance(expires, (int, float)):
            if expires < now_ms:
                continue  # skip expired entries entirely
            score += float(expires) / 1e15

        if score > best_score:
            best_score = score
            best = entry

    if best is None:
        raise TokenError("Token cache has no usable entries")
    return best


def read_desktop_credentials_from_dir(claude_dir: Path) -> dict:
    config_path = claude_dir / "config.json"
    if not config_path.is_file():
        raise TokenError(f"No config.json in {claude_dir}")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    encrypted = config.get(_CACHE_KEY)
    if not encrypted:
        raise TokenError(f"No {_CACHE_KEY} in {config_path}")

    master = _chromium_master_key(claude_dir)
    plain = _decrypt_token_cache(master, encrypted)
    cache = json.loads(plain)
    if not isinstance(cache, dict):
        raise TokenError("Token cache is not a JSON object")

    entry = _pick_cache_entry(cache)
    token = (entry.get("token") or entry.get("accessToken") or "").strip()
    if not token:
        raise TokenError("Cache entry has no token")

    plan = _format_plan(
        entry.get("subscriptionType"),
        entry.get("rateLimitTier"),
    )
    return {
        "token": token,
        "plan": plan,
        "raw": entry,
        "source": f"claude-desktop:{claude_dir}",
    }


def read_desktop_credentials() -> dict:
    if sys.platform not in ("win32", "darwin", "linux"):
        raise TokenError(f"Unsupported platform: {sys.platform}")

    last_error: Optional[str] = None
    for claude_dir in claude_desktop_dirs():
        try:
            return read_desktop_credentials_from_dir(claude_dir)
        except TokenError as e:
            last_error = str(e)
        except Exception as e:
            last_error = f"{claude_dir}: {e}"

    msg = "Claude Desktop credentials not found."
    if last_error:
        msg += f" Last error: {last_error}"
    raise TokenError(msg)


def try_read_desktop_credentials() -> Optional[dict]:
    try:
        return read_desktop_credentials()
    except TokenError:
        return None
