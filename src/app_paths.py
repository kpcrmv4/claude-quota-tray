"""
Resolve install layout: source tree (.venv + src/) vs PyInstaller .exe.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """Directory containing src/ or the .exe (install root)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def main_script() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve()
    return project_root() / "src" / "main.py"


def venv_pythonw() -> Optional[Path]:
    import app_platform as plat
    return plat.venv_pythonw(project_root())


def venv_python() -> Optional[Path]:
    import app_platform as plat
    return plat.venv_python(project_root())


def is_source_install() -> bool:
    root = project_root()
    return (root / "src" / "main.py").is_file() and venv_pythonw() is not None


def maintenance_script(name: str) -> Optional[Path]:
    """Find Setup / Run / Update / Uninstall .bat next to project root."""
    root = project_root()
    candidates = [
        root / f"{name} claude quota tray.bat",
        root / f"{name}.bat",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def maintenance_scripts() -> dict[str, Optional[Path]]:
    return {
        "setup": maintenance_script("Setup"),
        "run": maintenance_script("Run"),
        "update": maintenance_script("Update"),
        "uninstall": maintenance_script("Uninstall"),
    }


def update_runner_script() -> Path:
    return project_root() / "src" / "update_runner.py"
