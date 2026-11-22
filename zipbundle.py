"""One zip of the project — for handing to a teammate or a reviewer.

    from packaging import build_zip
    path = build_zip()

What goes in: source, web assets, docs, scripts, README, .env.example.
What stays out: .env (contains the API key), .packages / .wheels (~150 MB of
wheels), data/cache and data/runs (PDFs and traces, reproducible), __pycache__.

The same file is served by the running app at /download/litpilot.zip, so "send me
the whole thing" is answerable with a URL instead of a folder.
"""

from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

INCLUDE_DIRS = ["tools", "web", "scripts", "docs"]
INCLUDE_FILES = ["README.md", ".env.example", ".gitignore"]
EXCLUDE_SUFFIXES = {".pyc", ".log", ".zip", ".exe", ".whl"}
EXCLUDE_PARTS = {"__pycache__", "data", "dist", ".packages", ".wheels", ".tmppip", ".git"}


def _iter_files() -> list[Path]:
    out: list[Path] = []
    for name in INCLUDE_FILES:
        p = ROOT / name
        if p.exists():
            out.append(p)
    out.extend(sorted(ROOT.glob("*.py")))
    for d in INCLUDE_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and not (set(p.parts) & EXCLUDE_PARTS):
                out.append(p)
    seen: set[Path] = set()
    keep: list[Path] = []
    for p in out:
        if p in seen or p.suffix in EXCLUDE_SUFFIXES or p.name == ".env":
            continue
        seen.add(p)
        keep.append(p)
    return keep


def build_zip(tag: str | None = None) -> Path:
    DIST.mkdir(parents=True, exist_ok=True)
    tag = tag or datetime.now().strftime("%Y%m%d-%H%M")
    target = DIST / f"litpilot-{tag}.zip"
    files = _iter_files()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in files:
            zf.write(p, Path("LitPilot") / p.relative_to(ROOT))
    return target
