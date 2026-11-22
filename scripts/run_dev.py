"""Dev entry point.

    python scripts/run_dev.py                       # 只有本机能访问
    LITPILOT_HOST=0.0.0.0 python scripts/run_dev.py  # 同一 wifi 的队友可访问
    LITPILOT_PORT=8123 python scripts/run_dev.py

Dependencies live in .packages (installed by scripts/bootstrap_deps.py) because the
machine's pip cannot write to a temp dir inside the sandbox. PATH is untouched.
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / ".packages")]
os.chdir(ROOT)

import uvicorn  # noqa: E402

import config  # noqa: E402


def _lan_ip() -> str:
    """Ask the OS which local address it would use to reach the internet."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


if __name__ == "__main__":
    host = os.environ.get("LITPILOT_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.environ.get("LITPILOT_PORT", "8000"))
    suffix = f"?k={config.SHARE_TOKEN}" if config.SHARE_TOKEN else ""
    print(f"  本机   http://127.0.0.1:{port}/{suffix}")
    if host == "0.0.0.0":
        print(f"  局域网 http://{_lan_ip()}:{port}/{suffix}   （同一 wifi 的队友用这个）")
    else:
        print("  局域网未开：设 LITPILOT_HOST=0.0.0.0 才对外监听")
    print(f"  模式   {'离线语料' if config.DEFAULT_MOCK else config.DEEPSEEK_MODEL}"
          f" | 访问口令 {'已设' if config.SHARE_TOKEN else '无'}")
    uvicorn.run("app:app", host=host, port=port, log_level="info")
