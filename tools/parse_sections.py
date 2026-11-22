"""Tool 3/6 — parse_sections.

Extracts per-page text and cuts it into named sections. Page numbers must survive
this step: every evidence item later points at a page, and "能翻到原文" is the
product claim judges will test by opening the PDF themselves.

Section detection is heading-regex based on purpose. It is cheap, explainable and
good enough for arXiv layouts; a layout model would be more accurate and much
harder to defend in a 3-minute demo.
"""

from __future__ import annotations

import re

from pypdf import PdfReader

import config
import mockdata
from schema import Paper, PaperStatus
from tools.base import ToolError

HEADINGS = [
    ("Abstract", r"^\s*(abstract|摘\s*要)\b"),
    ("Introduction", r"^\s*(1\.?\s*)?(introduction|引\s*言)\b"),
    ("Related Work", r"^\s*(2\.?\s*)?(related work|background|相关工作)\b"),
    ("Method", r"^\s*(\d\.?\s*)?(method|methods|methodology|approach|our approach|方\s*法)\b"),
    ("Experiments", r"^\s*(\d\.?\s*)?(experiment|experiments|experimental setup|evaluation|实\s*验)\b"),
    ("Results", r"^\s*(\d\.?\s*)?(results|result|results and discussion|结\s*果)\b"),
    ("Conclusion", r"^\s*(\d\.?\s*)?(conclusion|conclusions|结\s*论)\b"),
    ("References", r"^\s*(references|bibliography|参考文献)\b"),
]
_COMPILED = [(name, re.compile(pat, re.IGNORECASE)) for name, pat in HEADINGS]


def _clean(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"-\n", "", text)          # de-hyphenate line breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _merge_duplicates(sections: list[dict]) -> list[dict]:
    """Real papers repeat headings (Results 4.1/4.2, or the word "Method" in refs).

    Duplicates are merged into the first occurrence instead of being kept separate:
    a subsection cut in half silently loses half the evidence, and the extraction
    step only reads a section by name once anyway.
    """
    merged: dict[str, dict] = {}
    for sec in sections:
        first = merged.get(sec["name"])
        if first is None:
            merged[sec["name"]] = dict(sec)
        else:
            first["text"] = (first["text"] + "\n\n" + sec["text"]).strip()
    return list(merged.values())


def split_sections(pages: list[str]) -> list[dict]:
    sections: list[dict] = []
    current = {"name": "Front Matter", "page": 1, "lines": []}
    for page_no, page_text in enumerate(pages, start=1):
        for line in page_text.split("\n"):
            stripped = line.strip()
            matched = None
            if stripped and len(stripped) < 80:
                for name, rx in _COMPILED:
                    if rx.match(stripped):
                        matched = name
                        break
            if matched:
                if current["lines"]:
                    sections.append(
                        {"name": current["name"], "page": current["page"],
                         "text": "\n".join(current["lines"]).strip()}
                    )
                current = {"name": matched, "page": page_no, "lines": []}
            else:
                current["lines"].append(line)
    if current["lines"]:
        sections.append(
            {"name": current["name"], "page": current["page"],
             "text": "\n".join(current["lines"]).strip()}
        )
    return [s for s in _merge_duplicates([s for s in sections if s["text"]]) if s["text"]]


def _read_pages(paper: Paper, mock: bool) -> list[str]:
    if mock:
        return mockdata.body_text(paper)
    if not paper.pdf_path:
        raise ToolError("parse_sections", "没有本地 PDF，无法解析", retryable=False)
    try:
        reader = PdfReader(paper.pdf_path)
        pages = []
        for page in reader.pages:
            pages.append(_clean(page.extract_text() or ""))
    except Exception as exc:  # noqa: BLE001
        raise ToolError("parse_sections", f"PDF 解析失败：{exc}") from exc
    if not pages or sum(len(p) for p in pages) < 500:
        raise ToolError("parse_sections", "抽取到的正文过少（可能是扫描版 PDF）")
    return pages


async def parse_sections(paper: Paper, *, mock: bool = False) -> dict:
    if paper.status != PaperStatus.FETCHED:
        raise ToolError("parse_sections", f"论文状态为 {paper.status.value}，无全文可解析", retryable=False)
    pages = _read_pages(paper, mock)
    sections = split_sections(pages)

    if not mock:
        out = config.TEXT_DIR / f"{paper.paper_id}.txt"
        with out.open("w", encoding="utf-8") as fh:
            for i, p in enumerate(pages, start=1):
                fh.write(f"[[page {i}]]\n{p}\n\n")
    return {
        "paper_id": paper.paper_id,
        "pages": pages,
        "sections": sections,
        "chars": sum(len(p) for p in pages),
    }
