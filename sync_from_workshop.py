#!/usr/bin/env python3
"""Sync tortoise.py from sibling workforce-tortise repo. Run before publishing to GitHub."""
from pathlib import Path

root = Path(__file__).resolve().parent
src = root.parent / "workforce-tortise" / "tortoise.py"
dst = root / "tortoise.py"
if not src.exists():
    raise SystemExit(f"Source not found: {src}\nClone workforce-tortise next to tortoise/")
text = src.read_text(encoding="utf-8")
# Full implementation for GitHub (replaces launcher stub)
dst.write_text(text)
# Local dev copy (launcher prefers this name when present)
(root / "tortoise_impl.py").write_text(text)
print(f"Synced -> {dst} and tortoise_impl.py ({len(text)} bytes)")
print("Safe to commit tortoise.py after ./scripts/check-secrets.sh")
