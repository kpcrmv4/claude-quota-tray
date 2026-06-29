"""Windows-specific platform helpers."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def acquire_single_instance() -> bool:
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW(None, True, "Local\\ClaudeQuotaTray_v1")
        return kernel32.GetLastError() != 183
    except Exception:
        return True


def already_running_message(app_name: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            f"{app_name} is already running.\nCheck the system tray (hidden icons area).",
            app_name,
            0x40,
        )
    except Exception:
        pass


def play_alert() -> None:
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        pass


def open_path(path: Path) -> None:
    os.startfile(path)  # type: ignore[attr-defined]


def open_claude_desktop() -> bool:
    local = os.environ.get("LOCALAPPDATA", "")
    candidates = []
    if local:
        candidates.append(Path(local) / "Programs" / "claude" / "Claude.exe")
        candidates.append(Path(local) / "Programs" / "Claude" / "Claude.exe")
    for exe in candidates:
        if exe.is_file():
            try:
                subprocess.Popen(
                    [str(exe)],
                    close_fds=True,
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                )
                return True
            except Exception:
                pass
    try:
        subprocess.Popen(["explorer.exe", "shell:AppsFolder"], close_fds=True)
        return True
    except Exception:
        return False


def venv_pythonw(project_root: Path) -> Optional[Path]:
    pyw = project_root / ".venv" / "Scripts" / "pythonw.exe"
    return pyw if pyw.is_file() else None


def venv_python(project_root: Path) -> Optional[Path]:
    py = project_root / ".venv" / "Scripts" / "python.exe"
    return py if py.is_file() else None


def detached_popen_kwargs() -> dict:
    return {
        "creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    }


def set_app_identity(app_user_model_id: str) -> None:
    """Separate this app from generic pythonw.exe in the taskbar and toasts."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_user_model_id)
    except Exception:
        pass
