"""Tool 4/6 — extract_claims.

Turns section text into structured fields plus claim/quote pairs. The single rule
that makes the rest of the system work: **every claim must carry a verbatim quote
copied from the supplied text**. The model is told to copy, not to paraphrase; the
verifier then checks whether it actually obeyed.

A quote that cannot be found is not a bug here — it is the signal the critic uses.
"""

from __future__ import annotations

import json

import config
import llm
import mockdata
from schema import Claim, Evidence, EvidenceLevel, ExtractedField, Metric, Paper
from tools.base import ToolError

SYSTEM = """你是一个严谨的科研文献抽取助手。你的输出必须是一个 JSON 对象，不要输出任何解释文字。

要求：
1. 每条 claim 的 quote 字段必须是输入文本中**逐字复制**的一段原文，不能改写、不能翻译、不能拼接。
2. 如果输入文本不足以支撑某个字段，该字段留空字符串，不要猜测。
3. metrics 只填论文自己报告的数值，格式如 {"name": "EM", "value": "46.2 (NaturalQuestions)"}。
4. claims 给 3-5 条，覆盖方法核心与主要结果。

输出 JSON 结构：
{
  "task": "研究任务（中文一句话）",
  "method": "方法名与核心做法（中文，30字内）",
  "dataset": "数据集名，多个用逗号分隔",
  "metrics": [{"name": "指标名", "value": "数值(数据集)"}],
  "baseline": "对比基线",
  "limitation": "论文自述或可推断的局限",
  "claims": [{"text": "结论（中文）", "quote": "verbatim English quote", "section": "Method|Results|..."}]
}"""

PRIORITY_SECTIONS = ("Method", "Experiments", "Results", "Introduction", "Conclusion")


def _build_context(sections: list[dict], budget: int) -> tuple[str, list[str]]:
    """Pick the most informative sections first, under a character budget."""
    picked: list[dict] = []
    used = 0
    ordered = sorted(
        sections,
        key=lambda s: PRIORITY_SECTIONS.index(s["name"]) if s["name"] in PRIORITY_SECTIONS else 99,
    )
    for sec in ordered:
        if sec["name"] == "References" or used >= budget:
            continue
        text = sec["text"][: budget - used]
        picked.append({**sec, "text": text})
        used += len(text)
    names = [s["name"] for s in picked]
    blocks = [f"<section name=\"{s['name']}\" page=\"{s['page']}\">\n{s['text']}\n</section>" for s in picked]
    return "\n\n".join(blocks), names


def _to_models(paper: Paper, data: dict, source: str) -> tuple[ExtractedField, list[Claim]]:
    metrics = []
    for m in data.get("metrics") or []:
        if isinstance(m, dict) and m.get("name"):
            metrics.append(Metric(name=str(m["name"])[:40], value=str(m.get("value", ""))[:60]))
    field = ExtractedField(
        paper_id=paper.paper_id,
        task=str(data.get("task", ""))[:120],
        method=str(data.get("method", ""))[:200],
        dataset=str(data.get("dataset", ""))[:120],
        metrics=metrics,
        baseline=str(data.get("baseline", ""))[:160],
        limitation=str(data.get("limitation", ""))[:200],
        source=source,
    )
    field.complete = bool(field.method and field.dataset and field.metrics)

    claims: list[Claim] = []
    raw_claims = data.get("claims") or []
    if not isinstance(raw_claims, list):
        raw_claims = []
    for i, rc in enumerate(raw_claims[:6]):
        if not isinstance(rc, dict):
            continue
        text = str(rc.get("text", "")).strip()
        quote = str(rc.get("quote", "")).strip()
        if not text:
            continue
        cid = f"{paper.paper_id}-c{i + 1}"
        claims.append(
            Claim(
                claim_id=cid,
                paper_id=paper.paper_id,
                text=text[:200],
                section=str(rc.get("section", ""))[:40],
                evidence=Evidence(
                    evid_id=f"{cid}-e",
                    paper_id=paper.paper_id,
                    claim_id=cid,
                    quote=quote[:600],
                    level=EvidenceLevel.C,  # provisional; verify_citation decides
                    note="待校验" if quote else "模型未给出原文引用",
                ),
            )
        )
    return field, claims


async def extract_claims(
    paper: Paper, sections: list[dict], *, mock: bool = False, from_abstract: bool = False
) -> tuple[ExtractedField, list[Claim], str]:
    """Returns (field, claims, label) where label describes what was fed to the model."""
    if mock:
        field, claims = mockdata.extract(paper, from_abstract=from_abstract)
        label = "摘要（仅摘要，无全文）" if from_abstract else f"全文 {sum(len(s['text']) for s in sections)} 字符"
        return field, claims, label

    if from_abstract:
        context = f"<section name=\"Abstract\">\n{paper.abstract}\n</section>"
        names = ["Abstract"]
        source = "abstract"
        label = "摘要（无全文）"
    else:
        context, names = _build_context(sections, config.EXTRACT_CHAR_BUDGET)
        source = "full_text"
        label = f"{len(names)} 节 / {len(context)} 字符"

    user = (
        f"论文标题：{paper.title}\n发表年份：{paper.year}\n\n"
        f"以下是论文正文片段：\n\n{context}\n\n"
        "请按系统要求输出 JSON。quote 必须从上面文本中逐字复制。"
    )
    try:
        data = await llm.chat_json(SYSTEM, user)
    except llm.LLMError as exc:
        raise ToolError("extract_claims", f"模型不可用：{exc}") from exc

    field, claims = _to_models(paper, data, source)
    if not claims:
        raise ToolError("extract_claims", "模型未返回任何带引用的结论")
    return field, claims, label


def dump_raw(field: ExtractedField, claims: list[Claim]) -> str:
    return json.dumps(
        {"field": field.model_dump(mode="json"), "claims": [c.model_dump(mode="json") for c in claims]},
        ensure_ascii=False,
    )
