"""Trace: every step of every run becomes one JSONL line and one SSE event.

The trace is not logging. It is the deliverable the judges look at: it proves the
system worked instead of a recorded video. Keep the event shape stable.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

from config import RUNS_DIR
from schema import TraceEvent


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


class Trace:
    """One run's trace: append-only JSONL + live fan-out queue."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.path: Path = RUNS_DIR / f"{run_id}.jsonl"
        self.path.touch(exist_ok=True)
        self.seq = 0
        self.queue: asyncio.Queue[dict] = asyncio.Queue()
        self._fh = self.path.open("a", encoding="utf-8")

    def emit(
        self,
        node: str,
        title: str,
        *,
        tool: str = "",
        status: str = "ok",
        detail: dict | None = None,
        decision: str = "",
    ) -> TraceEvent:
        self.seq += 1
        ev = TraceEvent(
            seq=self.seq,
            ts=_now(),
            run_id=self.run_id,
            node=node,
            tool=tool,
            status=status,
            title=title,
            detail=detail or {},
            decision=decision,
        )
        line = ev.model_dump_json()
        self._fh.write(line + "\n")
        self._fh.flush()
        self.queue.put_nowait(ev.model_dump())
        return ev

    async def pause(self, seconds: float = 0.0) -> None:
        """Small human-visible beat so the live replay is readable."""
        if seconds > 0:
            await asyncio.sleep(seconds)

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass

    def replay(self) -> list[dict]:
        out: list[dict] = []
        if not self.path.exists():
            return out
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return out


def load_trace(run_id: str) -> list[dict]:
    path = RUNS_DIR / f"{run_id}.jsonl"
    if not path.exists():
        return []
    items = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return items


def list_runs() -> list[dict]:
    runs = []
    for p in sorted(RUNS_DIR.glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
        runs.append(
            {
                "run_id": p.stem,
                "mtime": datetime.fromtimestamp(p.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
                "events": sum(1 for _ in p.open("r", encoding="utf-8")),
            }
        )
    return runs[:50]
