"""Shared tool plumbing.

A tool either returns a typed result or raises ToolError with a human-readable
reason. The executor turns every ToolError into a visible trace event — silent
failure is the one thing this project must never do.
"""

from __future__ import annotations

from dataclasses import dataclass


class ToolError(RuntimeError):
    def __init__(self, tool: str, reason: str, *, retryable: bool = True) -> None:
        super().__init__(f"{tool}: {reason}")
        self.tool = tool
        self.reason = reason
        self.retryable = retryable


@dataclass
class ToolCall:
    name: str
    args: dict


TOOL_SPECS: list[dict] = [
    {
        "name": "search_papers",
        "cn": "检索候选论文",
        "desc": "按主题英文关键词调用 arXiv / Semantic Scholar，返回候选论文元数据。",
        "io": "in: queries[] -> out: Paper[]",
    },
    {
        "name": "fetch_pdf",
        "cn": "取回全文",
        "desc": "下载 PDF 到本地缓存；失败则降级为仅摘要，并记录失败原因。",
        "io": "in: Paper -> out: pdf_path, status",
    },
    {
        "name": "parse_sections",
        "cn": "切分章节",
        "desc": "pypdf 抽取正文并按 Abstract/Method/Experiments/Results 等切分，保留页码。",
        "io": "in: pdf -> out: sections[], pages[]",
    },
    {
        "name": "extract_claims",
        "cn": "抽取结构化字段与结论",
        "desc": "对章节文本做结构化抽取，每条结论必须给出原文引用句。",
        "io": "in: sections -> out: ExtractedField, Claim[]",
    },
    {
        "name": "build_table",
        "cn": "生成对比表",
        "desc": "把多篇论文的 method/dataset/metric 对齐成一张表，并统计字段完整率。",
        "io": "in: ExtractedField[] -> out: TableRow[]",
    },
    {
        "name": "verify_citation",
        "cn": "校验引用",
        "desc": "把结论引用句回查到全文，给出 A/B/C/D 证据等级与页码。",
        "io": "in: Claim -> out: Evidence(level, page, ratio)",
    },
]
