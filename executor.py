"""Executor + Critic: the loop that actually runs a review.

Order is fixed by the design document:

    plan -> search -> (fetch, parse, extract, verify) x N -> table -> critic -> table -> metrics

The Critic is not a second model call. It is a rule: *any claim that is not backed by
locatable full text gets its paper re-fetched and re-extracted once, and if it still
fails it is marked and excluded.* Making it a rule instead of an opinion is what lets
you state the failure rate in the report.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime

import config
import llm
import mockdata
import planner
from schema import (
    Claim, EvidenceLevel, ExtractedField, Metrics, Paper, PaperStatus, RunResult,
    TableRow,
)
from tools import build_rows, compare_paragraph, ccr, fetch_pdf, parse_sections
from tools import extract_claims, search_papers, verify_citation
from tools.base import ToolError
from tools.verify_citation import normalize
from trace import Trace

LEVELS = ["A", "B", "C", "D"]


@dataclass
class State:
    topic: str
    mock: bool
    inject_fault: bool
    papers: list[Paper] = field(default_factory=list)
    pages: dict[str, list[str]] = field(default_factory=dict)
    sections: dict[str, list[dict]] = field(default_factory=dict)
    fields: dict[str, ExtractedField] = field(default_factory=dict)
    claims: dict[str, list[Claim]] = field(default_factory=dict)
    rows: list[TableRow] = field(default_factory=list)
    failures: int = 0
    retries: int = 0

    def all_claims(self) -> list[Claim]:
        return [c for cs in self.claims.values() for c in cs]


def _short(title: str, n: int = 46) -> str:
    return title if len(title) <= n else title[: n - 1] + "…"


def _level_counts(claims: list[Claim]) -> dict[str, int]:
    d = {k: 0 for k in LEVELS}
    for c in claims:
        d[c.level.value] += 1
    return d


async def _first_pass_paper(st: State, tr: Trace, paper: Paper, index: int) -> None:
    """fetch -> parse -> extract -> verify for one paper. Failures degrade, never raise."""
    tag = _short(paper.title)
    fault = st.inject_fault and index == 2  # the third paper times out, once

    try:
        await fetch_pdf(paper, mock=st.mock, fault=fault)
        tr.emit(
            "fetch", f"《{tag}》全文就绪", tool="fetch_pdf", status="ok",
            detail={
                "paper_id": paper.paper_id,
                "from_cache": paper.fetched_from_cache,
                "page_hint": "本地缓存" if paper.fetched_from_cache else "在线下载",
            },
        )
    except ToolError as exc:
        st.failures += 1
        paper.status = PaperStatus.SUMMARY_ONLY
        tr.emit(
            "fetch", f"《{tag}》下载失败：{exc.reason}", tool="fetch_pdf", status="error",
            detail={"paper_id": paper.paper_id, "reason": exc.reason, "retryable": exc.retryable},
            decision="降级：先用摘要抽取，标为 C 级，交给 Critic 重试",
        )
        await tr.pause(0.2)
        await _extract(st, tr, paper, index, from_abstract=True)
        return

    await tr.pause(0.15)
    await _parse_and_extract(st, tr, paper, index)


async def _parse_and_extract(st: State, tr: Trace, paper: Paper, index: int, *, retry: bool = False) -> None:
    tag = _short(paper.title)
    status = "retry" if retry else "ok"
    try:
        parsed = await parse_sections(paper, mock=st.mock)
    except ToolError as exc:
        st.failures += 1
        paper.status = PaperStatus.PARSE_FAILED
        tr.emit(
            "parse", f"《{tag}》章节切分失败：{exc.reason}", tool="parse_sections", status="error",
            detail={"paper_id": paper.paper_id, "reason": exc.reason},
            decision="降级：退回摘要抽取，该篇结论最高 C 级",
        )
        await _extract(st, tr, paper, index, from_abstract=True)
        return

    st.pages[paper.paper_id] = parsed["pages"]
    st.sections[paper.paper_id] = parsed["sections"]
    names = [s["name"] for s in parsed["sections"]]
    tr.emit(
        "parse", f"《{tag}》切出 {len(names)} 个章节 / 正文 {parsed['chars']} 字符",
        tool="parse_sections", status=status,
        detail={"paper_id": paper.paper_id, "pages": len(parsed["pages"]), "sections": names},
        decision="Method / Experiments / Results 优先送入抽取" if not retry else "重试：重新切分并抽取",
    )
    await tr.pause(0.15)
    await _extract(st, tr, paper, index, from_abstract=False, retry=retry)


async def _extract(st: State, tr: Trace, paper: Paper, index: int, *, from_abstract: bool, retry: bool = False) -> None:
    tag = _short(paper.title)
    sections = [] if from_abstract else st.sections.get(paper.paper_id, [])
    status = "retry" if retry else "ok"

    attempt = 0
    while True:
        try:
            field, claims, label = await extract_claims(
                paper, sections, mock=st.mock, from_abstract=from_abstract
            )
            break
        except ToolError as exc:
            attempt += 1
            if not exc.retryable or attempt > config.MAX_EXTRACT_RETRY:
                st.failures += 1
                tr.emit(
                    "extract", f"《{tag}》抽取失败：{exc.reason}", tool="extract_claims", status="error",
                    detail={"paper_id": paper.paper_id, "reason": exc.reason, "attempts": attempt},
                    decision="该篇不产出结论，失败原因写入 trace",
                )
                st.claims.setdefault(paper.paper_id, [])
                return
            st.retries += 1
            tr.emit(
                "extract", f"《{tag}》抽取失败，第 {attempt} 次重试", tool="extract_claims", status="retry",
                detail={"paper_id": paper.paper_id, "reason": exc.reason},
            )
            await tr.pause(0.25)

    st.fields[paper.paper_id] = field
    st.claims[paper.paper_id] = claims
    tr.emit(
        "extract", f"《{tag}》抽取完成：{len(claims)} 条结论",
        tool="extract_claims", status=status,
        detail={
            "paper_id": paper.paper_id,
            "input": label,
            "method": field.method,
            "dataset": field.dataset,
            "metrics": [f"{m.name}={m.value}" for m in field.metrics],
            "complete": field.complete,
        },
        decision="进入证据校验" if not retry else "重试结果进入证据校验",
    )
    await tr.pause(0.15)
    await _verify(st, tr, paper, retry=retry)


async def _verify(st: State, tr: Trace, paper: Paper, *, retry: bool = False) -> None:
    claims = st.claims.get(paper.paper_id, [])
    if not claims:
        return
    pages = st.pages.get(paper.paper_id)
    for claim in claims:
        if claim.evidence:
            claim.evidence = verify_citation(claim.evidence, paper, pages)

    counts = _level_counts(claims)
    bad = counts["C"] + counts["D"]
    tr.emit(
        "verify",
        f"《{_short(paper.title)}》{len(claims)} 条结论校验：A{counts['A']} / B{counts['B']} / C{counts['C']}",
        tool="verify_citation",
        status="retry" if retry else ("warn" if bad else "ok"),
        detail={
            "paper_id": paper.paper_id,
            "claims": [
                {
                    "claim_id": c.claim_id,
                    "text": c.text,
                    "quote": c.evidence.quote if c.evidence else "",
                    "level": c.level.value,
                    "page": c.evidence.page if c.evidence else None,
                    "ratio": c.evidence.match_ratio if c.evidence else 0,
                    "note": c.evidence.note if c.evidence else "",
                }
                for c in claims
            ],
        },
        decision="全部可核对" if not bad else f"{bad} 条不可核对，进入 Critic 复核",
    )
    await tr.pause(0.12)


def _build(st: State, tr: Trace, *, final: bool) -> None:
    st.rows = build_rows(st.papers, st.fields, st.claims)
    usable = sum(1 for r in st.rows if r.used_in_conclusion)
    tr.emit(
        "table",
        f"对比表{'重建' if final else '生成'}：{len(st.rows)} 行，{usable} 行进入结论",
        tool="build_table",
        status="ok" if usable else "warn",
        detail={
            "rows": [
                {
                    "paper_id": r.paper_id,
                    "title": _short(r.title, 30),
                    "method": r.method,
                    "dataset": r.dataset,
                    "metrics": [f"{m.name}={m.value}" for m in r.metrics],
                    "worst_level": r.worst_level.value,
                    "used_in_conclusion": r.used_in_conclusion,
                }
                for r in st.rows
            ]
        },
        decision="按论文年份降序排列，最弱证据等级随行显示",
    )


async def _critic(st: State, tr: Trace) -> None:
    """Re-fetch anything whose conclusions are not backed by locatable full text."""
    suspects = []
    for i, paper in enumerate(st.papers):
        claims = st.claims.get(paper.paper_id, [])
        if not claims:
            continue
        weak = [c for c in claims if c.level not in (EvidenceLevel.A, EvidenceLevel.B)]
        if weak:
            suspects.append((paper, weak, i))

    if not suspects:
        tr.emit("critic", "复核：所有结论均有可定位出处", status="ok",
                decision="无需重试，直接进入指标统计")
        await tr.pause(0.2)
        return

    for paper, weak, idx in suspects:
        tag = _short(paper.title)
        reason = "仅有摘要，无全文" if paper.status != PaperStatus.FETCHED else "引句未能在全文中定位"
        tr.emit(
            "critic", f"复核《{tag}》：{len(weak)} 条结论证据不足（{reason}）",
            status="warn",
            detail={"paper_id": paper.paper_id, "weak_claims": len(weak), "reason": reason},
            decision="重拉全文 → 重解析 → 重抽取 → 重校验（第 2 次尝试）",
        )
        await tr.pause(0.25)
        st.retries += 1
        before = _level_counts(st.claims.get(paper.paper_id, []))

        try:
            await fetch_pdf(paper, mock=st.mock, fault=False)
            tr.emit("fetch", f"《{tag}》重拉全文成功", tool="fetch_pdf", status="retry",
                    detail={"paper_id": paper.paper_id, "attempt": 2})
        except ToolError as exc:
            st.failures += 1
            tr.emit("fetch", f"《{tag}》重拉仍然失败：{exc.reason}", tool="fetch_pdf", status="error",
                    detail={"paper_id": paper.paper_id, "reason": exc.reason},
                    decision="保持 C 级，不进入最终结论")
            continue

        await _parse_and_extract(st, tr, paper, idx, retry=True)

        after = _level_counts(st.claims.get(paper.paper_id, []))
        if after["A"] + after["B"] > before["A"] + before["B"]:
            tr.emit(
                "critic",
                f"复核通过《{tag}》：C 级 {before['C']} 条 → A/B 级 {after['A'] + after['B']} 条",
                status="ok",
                detail={"paper_id": paper.paper_id, "before": before, "after": after},
                decision="该篇结论重新进入比较表",
            )
        else:
            tr.emit(
                "critic", f"复核未通过《{tag}》：重试后仍无法定位出处",
                status="error",
                detail={"paper_id": paper.paper_id, "before": before, "after": after},
                decision="标为 C 级，不进入最终结论（失败保留在表内可见）",
            )
        await tr.pause(0.2)


def _metrics(st: State, duration: float) -> Metrics:
    all_claims = st.all_claims()
    rate, ok, total = ccr(all_claims)
    extracted = [f for f in st.fields.values()]
    complete = sum(1 for f in extracted if f.complete)
    u = llm.usage()
    return Metrics(
        ccr=rate,
        claims_total=total,
        claims_verified=ok,
        field_completeness=round(complete / len(extracted), 3) if extracted else 0.0,
        level_dist=_level_counts(all_claims),
        extract_retries=st.retries,
        failures=st.failures,
        failures_visible=st.failures,  # every failure is emitted as its own trace event
        papers_total=len(st.papers),
        duration_s=round(duration, 2),
        llm_calls=u["calls"],
        llm_tokens=u["tokens"],
        cost_usd=u["cost_usd"],
    )


def _result(run_id: str, st: State, plan: dict, metrics: Metrics, started: str) -> RunResult:
    return RunResult(
        run_id=run_id,
        topic=st.topic,
        mock=st.mock,
        plan=plan["steps"],
        papers=st.papers,
        fields=list(st.fields.values()),
        claims=st.all_claims(),
        table=st.rows,
        metrics=metrics,
        started_at=started,
        finished_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )


async def execute(
    run_id: str, topic: str, *, mock: bool, inject_fault: bool, trace: Trace | None = None
) -> RunResult:
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    t0 = time.perf_counter()
    llm.reset_usage()  # 成本按"这一轮"统计，别把进程里更早那几轮算进来
    tr = trace or Trace(run_id)
    st = State(topic=topic, mock=mock, inject_fault=inject_fault)

    tr.emit("planner", f"开始：「{_short(topic, 40)}」", status="info",
            detail={"mode": "mock（离线演示语料）" if mock else "live（arXiv + DeepSeek）",
                    "llm": "ready" if config.llm_ready() else "missing key"})
    plan = await planner.make_plan(topic, mock=mock)
    tr.emit("planner", "拆解为 5 个子任务", detail=plan, decision="串行执行；任一工具失败即降级，不中断整轮")
    await tr.pause(0.3)

    try:
        papers, source = await search_papers(plan["queries"], mock=mock)
    except ToolError as exc:
        st.failures += 1
        tr.emit("search", f"检索失败：{exc.reason}", tool="search_papers", status="error",
                detail={"reason": exc.reason}, decision="本轮无候选，直接输出空结果与失败原因")
        papers, source = [], "failed"

    st.papers = papers[: config.PAPER_LIMIT]
    tr.emit(
        "search", f"检索到 {len(st.papers)} 篇候选（{source}，近 {config.RECENT_YEARS} 年）",
        tool="search_papers", status="ok" if st.papers else "error",
        detail={
            "source": source,
            "queries": plan["queries"],
            "papers": [{"paper_id": p.paper_id, "title": p.title, "year": p.year} for p in st.papers],
        },
        decision=f"取前 {len(st.papers)} 篇进入抽取流程",
    )
    await tr.pause(0.3)

    for i, paper in enumerate(st.papers):
        tr.emit("planner", f"处理第 {i + 1}/{len(st.papers)} 篇：《{_short(paper.title, 40)}》",
                status="info", detail={"paper_id": paper.paper_id})
        await _first_pass_paper(st, tr, paper, i)

    _build(st, tr, final=False)
    await tr.pause(0.25)
    await _critic(st, tr)
    _build(st, tr, final=True)

    metrics = _metrics(st, time.perf_counter() - t0)
    tr.emit(
        "metrics", f"指标：CCR {metrics.ccr:.0%}（{metrics.claims_verified}/{metrics.claims_total}）"
                   f"，字段完整率 {metrics.field_completeness:.0%}",
        status="ok",
        detail=metrics.model_dump(mode="json"),
        decision=(f"{metrics.failures} 次失败全部可见，{metrics.extract_retries} 次重试"
                  + (f"，本轮 {metrics.llm_calls} 次模型调用 / {metrics.llm_tokens} tokens"
                     f" / ${metrics.cost_usd:.4f}" if metrics.llm_calls else "，离线语料未调用模型")),
    )

    result = _result(run_id, st, plan, metrics, started)
    (config.RUNS_DIR / f"{run_id}.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    tr.emit("done", "运行结束，可回放", status="ok",
            detail={"duration_s": metrics.duration_s, "run_id": run_id},
            decision=compare_paragraph(st.rows))
    tr.close()
    return result
