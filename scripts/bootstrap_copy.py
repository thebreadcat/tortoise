#!/usr/bin/env python3
"""One-time helper: copy tortoise.py from sibling workshop repo."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
src = root.parent / "workforce-tortise" / "tortoise.py"
dst = root / "tortoise.py"
if not src.is_file():
    raise SystemExit(
        f"Source not found: {src}\n"
        "Clone workforce-tortise as a sibling folder, or copy tortoise.py manually."
    )
dst.write_text(src.read_text(encoding="utf-8"))
print(f"Copied {src} -> {dst} ({dst.stat().st_size} bytes)")
