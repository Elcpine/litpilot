"""FastAPI surface.

Four endpoints carry the whole product story:

    POST /api/runs                 start a run, return its id immediately
    GET  /api/runs/{id}/stream     SSE — replay from JSONL, then live events
    GET  /api/runs/{id}/result     final table + metrics + every claim
    GET  /api/tools                the six tools, for the UI's tool legend

The SSE endpoint replays the JSONL file before switching to the live queue. That is
what makes "刷新页面不丢进度" true instead of a promise: the file is the source of
truth, the queue is only a convenience.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.responses import HTMLResponse, JSONResponse, Response

import config
from executor import execute
from schema import RunResult
from tools.base import TOOL_SPECS
from trace import Trace, list_runs

app = FastAPI(title="LitPilot", version="1.0")

RUNS: dict[str, dict] = {}

# 额度和并发只存在进程内存里：单进程单容器部署时它就是真话，重启即清零也正好
# 符合"演示当天重新开始"的预期。多 worker 部署会让它失效——所以 Dockerfile 里
# 只跑一个 uvicorn 进程，这是刻意选择，不是省事。
_BUDGET = {"day": "", "used": 0}


def _spend_one() -> None:
    day = datetime.now().strftime("%Y-%m-%d")
    if _BUDGET["day"] != day:
        _BUDGET["day"], _BUDGET["used"] = day, 0
    _BUDGET["used"] += 1


def _budget_left() -> int:
    day = datetime.now().strftime("%Y-%m-%d")
    used = _BUDGET["used"] if _BUDGET["day"] == day else 0
    return max(0, config.RUN_BUDGET - used)


class ShareGate:
    """可选访问口令：`?k=<口令>` 首访写 cookie，之后所有请求（含 SSE）自动带上。

    Why not HTTP Basic auth: EventSource cannot send custom headers, and a cookie is
    the one credential the browser attaches to a streaming request by itself.
    """

    def __init__(self, app) -> None:  # noqa: A002 - ASGI signature
        self.app = app

    async def __call__(self, scope, receive, send):
        token = config.SHARE_TOKEN
        if scope["type"] != "http" or not token:
            await self.app(scope, receive, send)
            return
        # /api/health 不设口令：托管平台（Render/Fly）用它做存活探针，
        # 探针带不了我们发的 cookie，设了口令就永远是 401、平台判定容器不健康。
        # 它只暴露"有没有配 key、今天还剩几次额度"，不暴露任何内容。
        if scope["path"] == "/api/health":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        if f"litpilot_k={token}" in headers.get("cookie", ""):
            await self.app(scope, receive, send)
            return
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        if query.get("k", [""])[0] == token:
            rest = [(k, v) for k, vs in query.items() if k != "k" for v in vs]
            target = scope["path"] + (f"?{urlencode(rest)}" if rest else "")
            resp = Response(status_code=303, headers={"Location": target})
            resp.set_cookie("litpilot_k", token, max_age=7 * 24 * 3600, httponly=True, samesite="lax")
            await resp(scope, receive, send)
            return
        if scope["path"].startswith("/api/"):
            resp = JSONResponse({"detail": "需要访问口令：在链接后加 ?k=<口令>"}, status_code=401)
        else:
            resp = HTMLResponse(
                "<h3>LitPilot</h3><p>需要访问口令：在链接后加 <code>?k=&lt;口令&gt;</code></p>",
                status_code=401,
            )
        await resp(scope, receive, send)


app.add_middleware(ShareGate)


class RunRequest(BaseModel):
    topic: str
    mock: bool | None = None
    inject_fault: bool | None = None


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "llm_ready": config.llm_ready(),
        "model": config.DEEPSEEK_MODEL,
        "default_mock": config.DEFAULT_MOCK,
        "papers_per_run": config.PAPER_LIMIT,
        "recent_years": config.RECENT_YEARS,
        "runs": sum(1 for _ in config.RUNS_DIR.glob("*.jsonl")),
        "budget_left": _budget_left(),
        "budget_total": config.RUN_BUDGET,
        "max_concurrent": config.MAX_CONCURRENT,
    }


@app.get("/api/tools")
async def tools() -> dict:
    return {"tools": TOOL_SPECS, "names": [t["name"] for t in TOOL_SPECS]}


@app.post("/api/runs")
async def create_run(req: RunRequest) -> dict:
    topic = req.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic 不能为空")
    if len(topic) > 200:
        raise HTTPException(status_code=400, detail="topic 过长（>200 字）")

    mock = config.DEFAULT_MOCK if req.mock is None else req.mock
    inject = mock if req.inject_fault is None else req.inject_fault
    if not mock and not config.llm_ready():
        raise HTTPException(
            status_code=400,
            detail="未配置 DEEPSEEK_API_KEY，无法运行真实模式。请在 .env 中填入 key，或勾选 mock 模式。",
        )

    running = sum(1 for e in RUNS.values() if not e["done"])
    if running >= config.MAX_CONCURRENT:
        raise HTTPException(
            status_code=429,
            detail=f"已有 {running} 个任务在运行（上限 {config.MAX_CONCURRENT}）。等它跑完再点，否则两个任务互相抢带宽，更容易触发下载超时。",
        )
    left = _budget_left()
    if left <= 0:
        raise HTTPException(
            status_code=429,
            detail=f"今天的运行额度已用完（{config.RUN_BUDGET} 次）。这是防止公网链接被转发后烧掉 API 额度的闸，明天自动恢复。",
        )
    _spend_one()

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    tr = Trace(run_id)
    RUNS[run_id] = {"queue": tr.queue, "trace": tr, "done": False, "topic": topic, "mock": mock}

    async def runner() -> None:
        entry = RUNS[run_id]
        try:
            await execute(run_id, topic, mock=mock, inject_fault=inject, trace=tr)
        except Exception as exc:  # noqa: BLE001 - the run must end with a visible reason
            tr.emit("done", f"运行异常终止：{type(exc).__name__}: {exc}", status="error",
                    detail={"error": repr(exc)}, decision="异常已记录，可复现")
            tr.close()
        finally:
            entry["done"] = True

    RUNS[run_id]["task"] = asyncio.create_task(runner())
    return {"run_id": run_id, "mock": mock, "inject_fault": inject, "topic": topic}


@app.get("/api/runs/{run_id}/stream")
async def stream(run_id: str) -> StreamingResponse:
    entry = RUNS.get(run_id)
    if entry is None and not (config.RUNS_DIR / f"{run_id}.jsonl").exists():
        raise HTTPException(status_code=404, detail="run 不存在")

    async def gen():
        seen = 0
        for ev in _replay(run_id):
            seen = ev.get("seq", seen)
            yield _sse(ev)
        if entry is None:
            yield "event: end\ndata: {}\n\n"
            return
        queue = entry["queue"]
        while True:
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=20)
            except asyncio.TimeoutError:
                if entry["done"]:
                    break
                yield ": keep-alive\n\n"
                continue
            if ev.get("seq", 0) <= seen:
                continue
            seen = ev["seq"]
            yield _sse(ev)
            if ev.get("node") == "done":
                break
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def _replay(run_id: str) -> list[dict]:
    path = config.RUNS_DIR / f"{run_id}.jsonl"
    out: list[dict] = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


@app.get("/api/runs/{run_id}/result")
async def result(run_id: str) -> dict:
    path = config.RUNS_DIR / f"{run_id}.json"
    if not path.exists():
        entry = RUNS.get(run_id)
        if entry and not entry["done"]:
            return {"status": "running", "run_id": run_id, "events": len(_replay(run_id))}
        raise HTTPException(status_code=404, detail="结果文件不存在")
    data = RunResult.model_validate_json(path.read_text(encoding="utf-8"))
    return {"status": "done", **data.model_dump(mode="json")}


@app.get("/api/runs")
async def runs() -> dict:
    return {"runs": list_runs()}


@app.get("/api/runs/{run_id}/trace")
async def trace(run_id: str) -> dict:
    return {"events": _replay(run_id)}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(config.WEB_DIR / "index.html")


@app.get("/download/litpilot.zip")
async def download() -> FileResponse:
    """Whole project as one zip. Built on request — 60 KB, ~40 ms, always fresh."""
    from zipbundle import build_zip

    path = build_zip()
    return FileResponse(
        path, media_type="application/zip", filename="litpilot.zip",
    )


app.mount("/web", StaticFiles(directory=str(config.WEB_DIR)), name="web")
