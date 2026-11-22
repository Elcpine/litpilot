"""End-to-end web smoke test (no browser): health -> start run -> SSE -> result.

    python scripts/smoke_web.py [port]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / ".packages")]

import httpx  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
BASE = f"http://127.0.0.1:{PORT}"


def main() -> None:
    with httpx.Client(timeout=30) as c:
        h = c.get(f"{BASE}/api/health").json()
        print("health:", h)
        assert h["ok"]

        idx = c.get(f"{BASE}/")
        print("index:", idx.status_code, len(idx.text), "bytes")
        assert idx.status_code == 200 and "LitPilot" in idx.text
        js = c.get(f"{BASE}/web/app.js")
        css = c.get(f"{BASE}/web/style.css")
        assert js.status_code == 200 and css.status_code == 200

        r = c.post(f"{BASE}/api/runs", json={
            "topic": "面向长文档的检索增强生成中片段切分与重排序的对比研究",
            "mock": True, "inject_fault": True,
        })
        assert r.status_code == 200, r.text
        run_id = r.json()["run_id"]
        print("run:", run_id)

        seen, deadline = 0, time.time() + 60
        nodes = []
        with c.stream("GET", f"{BASE}/api/runs/{run_id}/stream") as s:
            for line in s.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                ev = json.loads(line[6:])
                seen += 1
                nodes.append(ev["node"])
                if ev["node"] == "done":
                    print("done:", ev["title"], "|", ev["decision"][:60])
                    break
                if time.time() > deadline:
                    raise SystemExit("timeout waiting for done")
        assert "critic" in nodes and "verify" in nodes, nodes
        print(f"sse events: {seen}, nodes: {nodes}")

        res = c.get(f"{BASE}/api/runs/{run_id}/result").json()
        assert res["status"] == "done"
        m = res["metrics"]
        print("metrics:", json.dumps(m, ensure_ascii=False))
        assert m["claims_total"] > 0 and m["failures"] >= 1
        assert len(res["table"]) == 5

        streams = c.get(f"{BASE}/api/runs/{run_id}/stream")
        print("replay of finished run:", streams.status_code, "events in body:", streams.text.count("data: "))
        print("history:", c.get(f"{BASE}/api/runs").json()["runs"][:2])
        print("tools:", c.get(f"{BASE}/api/tools").json()["names"])
    print("\nWEB OK")


if __name__ == "__main__":
    main()
