"""Tool 5/6 — build_table.

Deterministic, no model call. Lays the extracted fields side by side and attaches
the worst evidence level on that paper, because a comparison table is only worth
reading if the weak cell is visible next to the strong ones.

A row whose worst level is C or D may still be shown — it is marked as "未进入结论"
rather than hidden. Hiding it is what a chat assistant does; showing it is what a
research assistant does.
"""

from __future__ import annotations

from schema import (
    Claim, EvidenceLevel, ExtractedField, Paper, PaperStatus, TableRow,
)

LEVEL_ORDER = [EvidenceLevel.A, EvidenceLevel.B, EvidenceLevel.C, EvidenceLevel.D]


def worst_level(claims: list[Claim]) -> EvidenceLevel:
    if not claims:
        return EvidenceLevel.D
    return max((c.evidence.level for c in claims if c.evidence), key=LEVEL_ORDER.index)


def build_rows(
    papers: list[Paper],
    fields: dict[str, ExtractedField],
    claims: dict[str, list[Claim]],
) -> list[TableRow]:
    rows: list[TableRow] = []
    for paper in papers:
        field = fields.get(paper.paper_id)
        paper_claims = claims.get(paper.paper_id, [])
        level = worst_level(paper_claims) if paper_claims else EvidenceLevel.C
        rows.append(
            TableRow(
                paper_id=paper.paper_id,
                title=paper.title,
                year=paper.year,
                venue=paper.venue,
                status=paper.status,
                task=field.task if field else "",
                method=field.method if field else "",
                dataset=field.dataset if field else "",
                metrics=list(field.metrics) if field else [],
                baseline=field.baseline if field else "",
                limitation=field.limitation if field else "",
                worst_level=level,
                source=field.source if field else "none",
                used_in_conclusion=level in (EvidenceLevel.A, EvidenceLevel.B),
                from_cache=paper.fetched_from_cache,
            )
        )
    return rows


def compare_paragraph(rows: list[TableRow]) -> str:
    """The one paragraph a human would actually read. Deterministic, no model."""
    usable = [r for r in rows if r.used_in_conclusion]
    if not usable:
        return "本轮没有达到可引用等级的证据，无法生成对比结论。详见 trace 中的失败与降级记录。"
    methods = "；".join(f"{r.method}（{r.year}，{r.worst_level.value} 级）" for r in usable if r.method)
    datasets = sorted({d.strip() for r in usable for d in r.dataset.split(",") if d.strip()})
    return (
        f"在 {len(usable)} 篇可引用工作中，方法路线可归为：{methods}。"
        f"共用数据集包括：{'、'.join(datasets[:6]) if datasets else '各篇差异较大'}。"
        f"另有 {len(rows) - len(usable)} 篇因证据等级不足未进入结论。"
    )
