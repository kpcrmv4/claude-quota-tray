"""
Check and apply updates from GitHub Releases.

Settings key ``update_github_repo``: ``owner/repo`` or full GitHub URL.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import config

_GITHUB_API = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
_REPO_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$",
    re.I,
)
_SKIP_DIRS = {".venv", ".git", "dist", "build", "__pycache__"}
_SKIP_FILES = {".DS_Store"}


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag: str
    html_url: str
    source_zip_url: Optional[str]
    exe_url: Optional[str]
    exe_name: Optional[str]


@dataclass(frozen=True)
class UpdateCheckResult:
    current_version: str
    latest: Optional[ReleaseInfo]
    update_available: bool
    error: Optional[str] = None
    # True when the repo exists but has no published release yet (GitHub 404
    # on releases/latest). This is a normal state, not an error.
    no_releases: bool = False


def parse_github_repo(spec: str) -> tuple[str, str]:
    """Return (owner, repo) from owner/repo or a github.com URL."""
    spec = (spec or "").strip()
    if not spec:
        raise ValueError("empty repository")
    if "/" in spec and "github.com" not in spec.lower():
        owner, repo = spec.split("/", 1)
        repo = repo.removesuffix(".git")
        return owner.strip(), repo.strip()
    m = _REPO_RE.match(spec)
    if m:
        return m.group(1), m.group(2)
    raise ValueError(f"Not a valid GitHub repo: {spec!r}")


def _parse_version(tag: str) -> tuple[int, ...]:
    tag = tag.strip().lstrip("vV")
    parts: list[int] = []
    for piece in re.split(r"[.\-+]", tag):
        if piece.isdigit():
            parts.append(int(piece))
        elif parts:
            break
    return tuple(parts) if parts else (0,)


def _version_gt(a: str, b: str) -> bool:
    return _parse_version(a) > _parse_version(b)


def _http_get_json(url: str, timeout: float = 30.0) -> dict:
    req = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{config.APP_NAME}/{config.APP_VERSION}",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download(url: str, dest: Path, timeout: float = 120.0) -> None:
    req = Request(url, headers={"User-Agent": f"{config.APP_NAME}/{config.APP_VERSION}"})
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(req, timeout=timeout) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)


def fetch_latest_release(owner: str, repo: str) -> ReleaseInfo:
    data = _http_get_json(_GITHUB_API.format(owner=owner, repo=repo))
    tag = str(data.get("tag_name") or "")
    version = tag.lstrip("vV") or "0"
    html_url = str(data.get("html_url") or f"https://github.com/{owner}/{repo}/releases")

    source_zip_url: Optional[str] = None
    exe_url: Optional[str] = None
    exe_name: Optional[str] = None

    for asset in data.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if not url:
            continue
        low = name.lower()
        if low.endswith(".zip") and "claude-quota-tray" in low and source_zip_url is None:
            source_zip_url = url
        elif low.endswith(".exe") and "claudequotatray" in low.replace("-", "").replace("_", ""):
            exe_url = url
            exe_name = name
        elif low.endswith(".zip") and source_zip_url is None and "source" in low:
            source_zip_url = url

    if source_zip_url is None:
        zipball = data.get("zipball_url")
        if zipball:
            source_zip_url = str(zipball)

    return ReleaseInfo(
        version=version,
        tag=tag,
        html_url=html_url,
        source_zip_url=source_zip_url,
        exe_url=exe_url,
        exe_name=exe_name,
    )


def check_for_update(repo_spec: str, current_version: str | None = None) -> UpdateCheckResult:
    current = current_version or config.APP_VERSION
    try:
        owner, repo = parse_github_repo(repo_spec)
        latest = fetch_latest_release(owner, repo)
        avail = _version_gt(latest.version, current)
        return UpdateCheckResult(
            current_version=current,
            latest=latest,
            update_available=avail,
        )
    except HTTPError as e:
        # 404 on releases/latest means the repo simply has no published
        # release yet — treat as a benign "nothing to update to" state.
        if e.code == 404:
            return UpdateCheckResult(
                current_version=current,
                latest=None,
                update_available=False,
                no_releases=True,
            )
        return UpdateCheckResult(
            current_version=current,
            latest=None,
            update_available=False,
            error=str(e),
        )
    except (URLError, ValueError, json.JSONDecodeError, KeyError) as e:
        return UpdateCheckResult(
            current_version=current,
            latest=None,
            update_available=False,
            error=str(e),
        )


def _copy_tree(src: Path, dest: Path) -> None:
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        if item.name in _SKIP_FILES:
            continue
        target = dest / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _find_extracted_root(extract_dir: Path) -> Path:
    """GitHub zipballs contain one top-level folder."""
    children = [p for p in extract_dir.iterdir() if p.name not in _SKIP_DIRS]
    if len(children) == 1 and children[0].is_dir():
        inner = children[0]
        if (inner / "src" / "main.py").is_file() or (inner / "requirements.txt").is_file():
            return inner
    if (extract_dir / "src" / "main.py").is_file():
        return extract_dir
    for child in children:
        if child.is_dir() and (child / "src" / "main.py").is_file():
            return child
    raise RuntimeError("Downloaded archive does not look like claude-quota-tray source")


def apply_source_update(project_dir: Path, release: ReleaseInfo) -> str:
    if not release.source_zip_url:
        raise RuntimeError("No source .zip asset on the latest release")

    with tempfile.TemporaryDirectory(prefix="cqt-update-") as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / "release.zip"
        _download(release.source_zip_url, zip_path)
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
        src_root = _find_extracted_root(extract_dir)
        _copy_tree(src_root, project_dir)

    venv_py = project_dir / ".venv" / "Scripts" / "python.exe"
    if venv_py.is_file():
        req = project_dir / "requirements.txt"
        if req.is_file():
            subprocess.run(
                [str(venv_py), "-m", "pip", "install", "-r", str(req), "--quiet",
                 "--disable-pip-version-check"],
                cwd=project_dir,
                check=True,
            )
    return f"Updated to {release.tag}"


def apply_exe_update(project_dir: Path, release: ReleaseInfo) -> str:
    if not release.exe_url or not release.exe_name:
        raise RuntimeError("No .exe asset on the latest release")

    dest = project_dir / release.exe_name
    staging = project_dir / f"{release.exe_name}.new"
    _download(release.exe_url, staging)
    running = Path(sys.executable).resolve()
    if dest.exists() and running == dest.resolve():
        bat = project_dir / "Apply Claude Quota Tray update.bat"
        bat.write_text(
            "@echo off\n"
            "timeout /t 3 /nobreak >nul\n"
            f'move /y "{staging.name}" "{dest.name}"\n'
            f'start "" "{dest.name}"\n'
            'del "%~f0"\n',
            encoding="utf-8",
        )
        if sys.platform == "win32":
            os.startfile(bat)  # type: ignore[attr-defined]
        return "Update will apply after you quit the app."
    if staging.exists():
        shutil.move(str(staging), str(dest))
    return f"Saved {dest.name}"


def apply_update(project_dir: Path, repo_spec: str, *, prefer_exe: bool = False) -> str:
    owner, repo = parse_github_repo(repo_spec)
    release = fetch_latest_release(owner, repo)
    if prefer_exe and release.exe_url:
        return apply_exe_update(project_dir, release)
    if (project_dir / "src" / "main.py").is_file():
        return apply_source_update(project_dir, release)
    if release.exe_url:
        return apply_exe_update(project_dir, release)
    raise RuntimeError("Cannot determine install type for update")
