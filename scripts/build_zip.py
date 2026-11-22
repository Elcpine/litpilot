"""CLI: python scripts/build_zip.py [tag]

Thin wrapper — the packaging rules live in zipbundle.py so the web app can serve
the exact same zip at /download/litpilot.zip.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT)]

from zipbundle import build_zip  # noqa: E402

if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else None
    path = build_zip(tag)
    with zipfile.ZipFile(path) as zf:
        n = len(zf.namelist())
    print(f"{path}  {n} files  {path.stat().st_size / 1024:.0f} KB")
