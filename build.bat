@echo off
REM Build script for Windows.
REM Uses .venv in this folder if present, else python on PATH.
REM Produces dist\ClaudeQuotaTray.exe (single-file, no console window).

SET APP_NAME=ClaudeQuotaTray
SET PYTHON=python

if exist ".venv\Scripts\python.exe" (
    SET "PYTHON=.venv\Scripts\python.exe"
    echo Using virtualenv: .venv
) else (
    echo Note: no .venv found — using default python. For a clean build, run Setup first.
)

echo === Checking PyInstaller ===
"%PYTHON%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not installed for this Python. Run:
    echo   "%PYTHON%" -m pip install -r requirements-dev.txt
    exit /b 1
)

echo === Cleaning previous build ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist %APP_NAME%.spec del %APP_NAME%.spec

if not exist "assets\app.ico" (
    echo [WARN] assets\app.ico not found — run: python scripts\generate_app_icon.py
)

echo === Building with PyInstaller ===
"%PYTHON%" -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name %APP_NAME% ^
    --icon assets\app.ico ^
    --paths src ^
    --hidden-import auth_discovery ^
    --hidden-import desktop_auth ^
    --hidden-import updater ^
    --hidden-import app_paths ^
    --hidden-import chart_widget ^
    --hidden-import desktop_widget ^
    --hidden-import ui_theme ^
    --hidden-import app_platform ^
    --hidden-import platform_win ^
    --hidden-import platform_darwin ^
    --collect-submodules Crypto ^
    src\main.py

if exist dist\%APP_NAME%.exe (
    echo.
    echo === BUILD OK ===
    echo Output: dist\%APP_NAME%.exe
    for %%I in (dist\%APP_NAME%.exe) do echo Size: %%~zI bytes
) else (
    echo === BUILD FAILED ===
    exit /b 1
)
