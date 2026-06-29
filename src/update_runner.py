"""
CLI entry for install maintenance (invoked from .bat or tray menu).

  python src/update_runner.py --check
  python src/update_runner.py --apply [--repo owner/repo]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import config
import settings as user_settings
from app_paths import is_frozen, is_source_install, project_root, venv_pythonw
from updater import apply_update, check_for_update, parse_github_repo


def _default_repo() -> str:
    return str(user_settings.get("update_github_repo") or config.DEFAULT_UPDATE_REPO)


def cmd_check(repo: str) -> int:
    result = check_for_update(repo)
    print(f"Current: v{result.current_version}")
    if result.error:
        print(f"Error: {result.error}", file=sys.stderr)
        return 1
    if not result.latest:
        print("Could not fetch release info.")
        return 1
    print(f"Latest:  {result.latest.tag} ({result.latest.html_url})")
    if result.update_available:
        print("Update available.")
        return 2
    print("Already up to date.")
    return 0


def cmd_apply(repo: str) -> int:
    root = project_root()
    prefer_exe = is_frozen() and not is_source_install()
    try:
        msg = apply_update(root, repo, prefer_exe=prefer_exe)
        print(msg)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if is_source_install():
        pyw = venv_pythonw()
        main = root / "src" / "main.py"
        if pyw and main.is_file():
            subprocess.Popen(
                [str(pyw), str(main)],
                cwd=root,
                creationflags=subprocess.DETACHED_PROCESS
                if sys.platform == "win32"
                else 0,
            )
            print("Restarted tray app.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Claude Quota Tray — updater")
    parser.add_argument("--check", action="store_true", help="Compare versions only")
    parser.add_argument("--apply", action="store_true", help="Download and apply latest release")
    parser.add_argument("--repo", default=None, help="GitHub owner/repo or URL")
    args = parser.parse_args(argv)

    repo = args.repo or _default_repo()
    try:
        parse_github_repo(repo)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if args.apply:
        return cmd_apply(repo)
    if args.check:
        return cmd_check(repo)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
