"""Live-mode probe: one real arXiv paper, end to end, with timing.

    python scripts/smoke_live.py ["query"] [max_papers]

Prints how much text we actually got, what the model extracted, and where every
claim landed on the evidence ladder. This is the script that decides whether real
PDFs are good enough for 12.05 — run it before promising anything.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / ".packages")]

import config  # noqa: E402
from tools import extract_claims, fetch_pdf, parse_sections, search_papers, verify_citation  # noqa: E402
from tools.base import ToolError  # noqa: E402


async def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "retrieval augmented generation chunking"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    print(f"key ready: {config.llm_ready()} | model: {config.DEEPSEEK_MODEL}")
    t0 = time.perf_counter()
    try:
        papers, source = await search_papers([query], mock=False)
    except ToolError as exc:
        print("SEARCH FAILED:", exc.reason)
        return
    print(f"search: {len(papers)} papers from {source} in {time.perf_counter() - t0:.1f}s")
    for p in papers[:limit]:
        print(f"  {p.paper_id:<22} {p.year}  {p.title[:70]}")

    for paper in papers[:limit]:
        print(f"\n=== {paper.paper_id} {paper.title[:60]}")
        t = time.perf_counter()
        try:
            await fetch_pdf(paper, mock=False)
            print(f"  fetch  ok  {time.perf_counter() - t:.1f}s  {paper.pdf_path}")
        except ToolError as exc:
            print(f"  fetch  FAILED  {exc.reason}")
            continue

        t = time.perf_counter()
        try:
            parsed = await parse_sections(paper, mock=False)
        except ToolError as exc:
            print(f"  parse  FAILED  {exc.reason}")
            continue
        secs = [s["name"] for s in parsed["sections"]]
        print(f"  parse  ok  {time.perf_counter() - t:.1f}s  pages={len(parsed['pages'])} "
              f"chars={parsed['chars']} sections={secs}")

        t = time.perf_counter()
        try:
            field, claims, label = await extract_claims(paper, parsed["sections"], mock=False)
        except ToolError as exc:
            print(f"  extract FAILED  {exc.reason}")
            continue
        print(f"  extract ok  {time.perf_counter() - t:.1f}s  input={label}")
        print(f"    method : {field.method[:90]}")
        print(f"    dataset: {field.dataset[:90]}")
        print(f"    metrics: {[f'{m.name}={m.value}' for m in field.metrics]}")
        for c in claims:
            ev = verify_citation(c.evidence, paper, parsed["pages"]) if c.evidence else None
            lvl = ev.level.value if ev else "D"
            note = ev.note if ev else "no evidence"
            print(f"    [{lvl}] {c.text[:60]}  <- {note[:70]}")


if __name__ == "__main__":
    asyncio.run(main())
