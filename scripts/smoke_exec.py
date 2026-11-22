"""Smoke test: run one full mock pipeline without the web layer.

    python scripts/smoke_exec.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / ".packages")]

import config  # noqa: E402
from executor import execute  # noqa: E402
from trace import load_trace  # noqa: E402


async def main() -> None:
    run_id = "smoke"
    (config.RUNS_DIR / f"{run_id}.jsonl").unlink(missing_ok=True)
    result = await execute(
        run_id, "面向长文档的检索增强生成中片段切分与重排序的对比研究", mock=True, inject_fault=True
    )
    print("=== metrics ===")
    print(result.metrics.model_dump_json(indent=2))
    print("\n=== table ===")
    for row in result.table:
        print(f"[{row.worst_level.value}] {row.title[:40]:42} {row.method[:30]:32} {row.dataset[:30]}")
    print("\n=== claims ===")
    for c in result.claims:
        print(f"{c.paper_id} {c.level.value} p{c.evidence.page} {c.text[:50]}")
    events = load_trace(run_id)
    print(f"\n=== trace: {len(events)} events ===")
    for ev in events:
        print(f"{ev['seq']:3} {ev['node']:<9} {ev['status']:<6} {ev['title']}")
    missing = [k for k in ("A", "B") if result.metrics.level_dist.get(k, 0) == 0]
    assert not missing, f"expected A and B levels in the demo story, missing {missing}"
    assert result.metrics.level_dist.get("C", 0) == 1, "one claim must stay C after the critic retry"
    assert result.metrics.failures >= 1, "fault injection should be visible"
    assert result.metrics.ccr < 1.0, "an unverifiable claim must lower the CCR"
    assert any(r.worst_level.value == "C" for r in result.table), "the C row must stay visible, marked"
    print("\nOK")


if __name__ == "__main__":
    asyncio.run(main())
