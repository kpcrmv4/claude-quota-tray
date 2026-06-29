"""
Multi-account support.

Each account points to a source for the OAuth/API token:
  - mode "auto": use the default discovery in token_reader
  - mode "file": read JSON from an explicit path

Tokens themselves are never stored in settings.json — we only store paths.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

import settings as user_settings
from token_reader import (
    TokenError, _extract_token, _find_first, _format_plan,
    _PLAN_KEYS, _RATE_TIER_KEYS, read_credentials,
)


def list_accounts() -> list[dict]:
    return user_settings.load().get("accounts", [])


def active_account() -> dict:
    data = user_settings.load()
    aid = data.get("active_account_id")
    accounts = data.get("accounts", [])
    if not accounts:
        raise TokenError("No accounts configured.")
    for a in accounts:
        if a.get("id") == aid:
            return a
    return accounts[0]


def set_active(account_id: str) -> None:
    data = user_settings.load()
    data["active_account_id"] = account_id
    user_settings.save(data)


def add_account(name: str, mode: str, path: Optional[str] = None) -> dict:
    if mode not in ("auto", "file"):
        raise ValueError(f"Unknown account mode: {mode}")
    new = {
        "id": str(uuid.uuid4()),
        "name": name or "Account",
        "mode": mode,
        "path": path,
    }
    data = user_settings.load()
    data["accounts"].append(new)
    user_settings.save(data)
    return new


def remove_account(account_id: str) -> None:
    data = user_settings.load()
    accounts = [a for a in data.get("accounts", []) if a.get("id") != account_id]
    if not accounts:
        return
    data["accounts"] = accounts
    if data.get("active_account_id") == account_id:
        data["active_account_id"] = accounts[0]["id"]
    user_settings.save(data)


def get_token(account: dict) -> str:
    """Backwards-compat: return just the token string."""
    return get_credentials(account)["token"]


def get_credentials(account: dict, exclude_tokens: Optional[set] = None) -> dict:
    """
    Return {"token": str, "plan": Optional[str]} for the given account.

    ``exclude_tokens`` is honoured for "auto" accounts so a token already
    known to be invalid is skipped in favour of the next discovery source.
    """
    mode = account.get("mode", "auto")
    if mode == "auto":
        return read_credentials(exclude_tokens=exclude_tokens)
    path = account.get("path")
    if not path:
        raise TokenError(f"Account '{account.get('name')}' has no path configured.")
    p = Path(path)
    if not p.exists():
        raise TokenError(f"Credentials file not found: {p}")
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise TokenError(f"Could not read {p}: {e}")
    token = _extract_token(data)
    if not token:
        raise TokenError(f"No recognisable token field in {p}")
    plan = _format_plan(
        _find_first(data, _PLAN_KEYS),
        _find_first(data, _RATE_TIER_KEYS),
    )
    return {"token": token, "plan": plan, "raw": data}
