#!/usr/bin/env python3
"""
Generate assets/app.ico for Windows shortcuts and PyInstaller.

Uses the same frame style as the live tray icon (icon_renderer).
Run from repo root: python scripts/generate_app_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402

from icon_renderer import render_icon  # noqa: E402

OUT = ROOT / "assets" / "app.ico"
SIZES = (16, 32, 48, 64, 128, 256)
# Representative usage % for a friendly default glyph (not error/100).
SAMPLE_PCT = 67


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    base = render_icon(SAMPLE_PCT, error=False, theme="dark", style="frame")
    images: list[Image.Image] = []
    for size in SIZES:
        if size == 256:
            images.append(base.copy())
        else:
            images.append(base.resize((size, size), Image.Resampling.LANCZOS))
    images[0].save(
        OUT,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=images[1:],
    )
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
