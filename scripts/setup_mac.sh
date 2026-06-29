#!/usr/bin/env bash
# First-time setup on macOS (run from repo root).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
echo "Done. Run: source .venv/bin/activate && python src/main.py"
