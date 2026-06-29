#!/usr/bin/env bash
# Build script for macOS / Linux. Run inside an activated virtualenv.
set -euo pipefail

APP_NAME="ClaudeQuotaTray"

echo "=== Cleaning previous build ==="
rm -rf build dist "${APP_NAME}.spec"

if [ ! -f "assets/app.ico" ]; then
    echo "[WARN] assets/app.ico not found — run: python scripts/generate_app_icon.py"
fi

echo "=== Building with PyInstaller ==="
ICON_ARGS=()
if [ -f "assets/app.ico" ]; then
    ICON_ARGS=(--icon assets/app.ico)
fi
pyinstaller \
    --onefile \
    --windowed \
    --name "$APP_NAME" \
    "${ICON_ARGS[@]}" \
    --paths src \
    --hidden-import auth_discovery \
    --hidden-import desktop_auth \
    --hidden-import updater \
    --hidden-import app_paths \
    --hidden-import chart_widget \
    --hidden-import desktop_widget \
    --hidden-import ui_theme \
    --hidden-import app_platform \
    --hidden-import platform_win \
    --hidden-import platform_darwin \
    --collect-submodules Crypto \
    src/main.py

if [ -f "dist/${APP_NAME}" ] || [ -d "dist/${APP_NAME}.app" ]; then
    echo
    echo "=== BUILD OK ==="
    ls -lh dist/
else
    echo "=== BUILD FAILED ==="
    exit 1
fi
