"""Bootstrap the runtime dependencies without pip.

Why this exists: on this machine `pip install` fails inside the agent sandbox
(PermissionError while writing its own temp unpack dir). Downloading wheels with
urllib and unzipping them ourselves avoids pip's temp handling entirely and keeps
the install reproducible for every teammate.

The resolver is deliberately small: top-level requirements are declared below,
and each downloaded wheel's METADATA is read for its own Requires-Dist. Extras
and environment markers that name `extra` are skipped; exact pins are honoured.

Usage:
    python scripts/bootstrap_deps.py           # install (idempotent)
    python scripts/bootstrap_deps.py --clean   # wipe .packages first
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / ".packages"
WHEELS = ROOT / ".wheels"

TOP_LEVEL = ["fastapi", "uvicorn", "httpx", "pypdf", "python-dotenv"]

PY_TAG = f"cp{sys.version_info.major}{sys.version_info.minor}"
PLATFORM = "win_amd64" if sys.platform == "win32" else "manylinux2014_x86_64"


# ------------------------------------------------------------------ wheel picking

def _pick_wheel(files: list[dict]) -> dict | None:
    ranked: list[tuple[int, dict]] = []
    for f in files:
        name = f["filename"]
        if not name.endswith(".whl"):
            continue
        bad = ("musllinux", "macosx", "i686", "aarch64", "arm64")
        if any(b in name for b in bad):
            continue
        if "none-any" in name:
            rank = 2
        elif PY_TAG in name and PLATFORM in name:
            rank = 0
        elif PY_TAG in name:
            rank = 1
        else:
            continue
        ranked.append((rank, f))
    if not ranked:
        return None
    ranked.sort(key=lambda x: x[0])
    return ranked[0][1]


def _download(url: str, dest: Path) -> Path:
    WHEELS.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=180) as r:
        dest.write_bytes(r.read())
    return dest


def fetch(name: str, pinned: str | None) -> Path:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=30) as r:
        meta = json.load(r)
    if pinned and pinned in meta["releases"]:
        chosen = _pick_wheel(meta["releases"][pinned])
    else:
        chosen = _pick_wheel(meta["urls"])
        if chosen is None:
            for v in reversed(list(meta["releases"])):
                chosen = _pick_wheel(meta["releases"][v])
                if chosen:
                    break
    if chosen is None:
        raise SystemExit(f"no compatible wheel for {name}")
    dest = WHEELS / chosen["filename"]
    if not (dest.exists() and dest.stat().st_size == chosen["size"]):
        _download(chosen["url"], dest)
    return dest


# ------------------------------------------------------------------ metadata

def requires(wheel: Path) -> list[tuple[str, str | None]]:
    """Parse Requires-Dist of a wheel into (name, exact_version|None)."""
    with zipfile.ZipFile(wheel) as zf:
        meta_name = next((n for n in zf.namelist() if n.endswith(".dist-info/METADATA")), None)
        if not meta_name:
            return []
        text = zf.read(meta_name).decode("utf-8", "replace")
    out: list[tuple[str, str | None]] = []
    for line in text.splitlines():
        if not line.startswith("Requires-Dist:"):
            continue
        spec = line.split(":", 1)[1].strip()
        if ";" in spec:
            req, marker = spec.split(";", 1)
            if "extra" in marker:
                continue
        else:
            req = spec
        req = req.strip()
        m = re.match(r"([A-Za-z0-9_.\-]+)\s*(?:\(([^)]*)\))?", req)
        if not m:
            continue
        name = m.group(1).replace("_", "-").lower()
        spec_part = (m.group(2) or "").strip()
        pinned = None
        if spec_part.startswith("=="):
            pinned = spec_part[2:].strip()
        out.append((name, pinned))
    return out


def unpack(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as zf:
        for item in zf.infolist():
            name = item.filename
            if name.endswith("/"):
                continue
            if ".data/" in name:
                name = name.split(".data/", 1)[1]
                if "/" in name:
                    name = name.split("/", 1)[1]
            if not name:
                continue
            out = TARGET / name
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(item) as src, out.open("wb") as dst:
                dst.write(src.read())


def main() -> None:
    if "--clean" in sys.argv and TARGET.exists():
        shutil.rmtree(TARGET, ignore_errors=True)
        print(f"removed {TARGET}")

    TARGET.mkdir(parents=True, exist_ok=True)
    queue: list[tuple[str, str | None]] = [(n, None) for n in TOP_LEVEL]
    done: dict[str, str] = {}
    while queue:
        name, pinned = queue.pop(0)
        if name in done:
            continue
        wheel = fetch(name, pinned)
        unpack(wheel)
        done[name] = wheel.name
        print(f"  ok  {wheel.name}")
        for dep, pin in requires(wheel):
            if dep not in done:
                queue.append((dep, pin))
    print(f"\ninstalled {len(done)} distributions into {TARGET}")


if __name__ == "__main__":
    main()
