"""Planner: turns one topic sentence into an executable, auditable five-step plan.

Two rules that come straight from the design document:

1. The five sub-tasks are fixed. A planner that improvises is a planner you cannot
   demo twice, and the judges will ask you to run it again.
2. The plan is printed before anything executes, so a wrong plan is caught before
   it costs eight minutes of PDF parsing.

Query expansion uses the model when a key is configured, and falls back to a
deterministic heuristic — the demo must survive a dead network.
"""

from __future__ import annotations

import re

import config
import llm

STEPS = [
    {
        "id": "S1",
        "name": "界定问题与边界",
        "goal": "把题目收敛成一个可检索的问题，并固定时间窗与论文数量",
        "tools": [],
    },
    {
        "id": "S2",
        "name": "检索近五年代表性工作",
        "goal": "用 2-3 条查询召回候选，按相关度取前 N 篇",
        "tools": ["search_papers"],
    },
    {
        "id": "S3",
        "name": "逐篇抽取 method / dataset / metric",
        "goal": "下载全文、切分章节、结构化抽取，每条结论附原文引用",
        "tools": ["fetch_pdf", "parse_sections", "extract_claims"],
    },
    {
        "id": "S4",
        "name": "横向对比技术路线",
        "goal": "生成字段对齐的对比表，并标出每行的最弱证据等级",
        "tools": ["build_table"],
    },
    {
        "id": "S5",
        "name": "核对每条结论出处",
        "goal": "逐条把引用句对回全文，定级 A/B/C/D，C 级触发重拉全文",
        "tools": ["verify_citation"],
    },
]

_CJK = re.compile(r"[\u4e00-\u9fff]")


def _heuristic_queries(topic: str) -> list[str]:
    base = re.sub(r"[，。！？、；：]", " ", topic).strip()
    base = re.sub(r"\s+", " ", base)
    words = [w for w in base.split(" ") if w]
    queries = [base]
    if len(words) >= 2:
        queries.append(" ".join(words[:2]))
    queries.append(f"{base} survey")
    seen, out = set(), []
    for q in queries:
        key = q.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(q)
    return out[:3]


async def _llm_queries(topic: str) -> list[str]:
    system = (
        "你是文献检索助手。把用户的研究题目转成 3 条 arXiv 英文检索式，"
        '只输出 JSON：{"queries": ["...", "...", "..."]}。检索式要短，2-6 个关键词。'
    )
    data = await llm.chat_json(system, f"研究题目：{topic}", temperature=0.0)
    queries = [str(q).strip() for q in (data.get("queries") or []) if str(q).strip()]
    if not queries:
        raise llm.LLMError("empty queries")
    return queries[:3]


async def make_plan(topic: str, *, mock: bool = False) -> dict:
    queries = _heuristic_queries(topic)
    source = "规则扩展"
    if not mock and config.llm_ready():
        try:
            queries = await _llm_queries(topic)
            source = "模型扩展"
        except Exception:  # noqa: BLE001 - planning must never block the run
            source = "规则扩展（模型不可用，已降级）"
    return {
        "topic": topic,
        "scope": f"近 {config.RECENT_YEARS} 年（{_recent_window()}），最多 {config.PAPER_LIMIT} 篇，仅英文可开放获取论文",
        "queries": queries,
        "query_source": source,
        "steps": STEPS,
        "mock": mock,
    }


def _recent_window() -> str:
    from datetime import date

    y = date.today().year
    return f"{y - config.RECENT_YEARS}-{y}"


def plan_summary(plan: dict) -> str:
    names = " → ".join(f"{s['id']} {s['name']}" for s in plan["steps"])
    return f"{names}；检索式：{' / '.join(plan['queries'])}"
