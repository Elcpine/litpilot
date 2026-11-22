"""Tool 6/6 — verify_citation. The only reason the product is credible.

Given a claim's quote, find it in the paper's full text and assign a level:

    A  found verbatim after normalization (whitespace, hyphenation, quotes)
    B  fuzzy match in the same page, ratio >= 0.95
    C  no full text, or the quote is not in it
    D  no quote at all (assigned by the caller; never appears in conclusions)

Normalization is deliberately conservative: it is allowed to fix typesetting, not
to fix meaning. Anything that survives only because we "cleaned it up" would be a
false A, which is worse than an honest C.
"""

from __future__ import annotations

import difflib
import re

from schema import Evidence, EvidenceLevel, Paper, PaperStatus

FUZZY_THRESHOLD = 0.95


def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u00ad", "")          # soft hyphen
    text = text.replace("\ufb01", "fi").replace("\ufb02", "fl")
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"-\s*\n\s*", "", text)      # hyphen split across lines
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _best_match(haystack: str, needle: str) -> tuple[float, int, bool]:
    """Return (coverage, offset, exact).

    Coverage is matched characters / len(quote), not difflib's symmetric ratio:
    the quote is the thing we are checking, and a quote embedded in a longer
    sentence must not be punished for the sentence's extra words.

    ``exact`` is what separates A from B. A quote whose every character is present
    can still be inexact — "fusion weight" inside "fusion weights" covers 100% of
    the quote, yet it is not verbatim. Only a plain substring hit earns level A.
    """
    if not needle:
        return 0.0, -1, False
    idx = haystack.find(needle)
    if idx != -1:
        return 1.0, idx, True
    if len(haystack) < len(needle):
        return 0.0, -1, False
    sm = difflib.SequenceMatcher(None, haystack, needle, autojunk=False)
    blocks = sm.get_matching_blocks()
    matched = sum(b.size for b in blocks)
    if matched == 0:
        return 0.0, -1, False
    coverage = min(1.0, matched / len(needle))
    first = blocks[0]
    start = max(0, first.a - first.b)
    return coverage, start, False


def verify_citation(claim_evidence: Evidence, paper: Paper, pages: list[str] | None) -> Evidence:
    ev = claim_evidence.model_copy(deep=True)
    ev.level = EvidenceLevel.C
    ev.match_ratio = 0.0

    if paper.status != PaperStatus.FETCHED or not pages:
        ev.note = "未取到全文，仅能依据摘要 —— 不进入最终结论"
        return ev

    if not ev.quote.strip():
        ev.level = EvidenceLevel.D
        ev.note = "模型未提供引用句"
        return ev

    needle = normalize(ev.quote)
    best_ratio, best_page, best_offset, best_exact = 0.0, None, None, False

    for page_no, page_text in enumerate(pages, start=1):
        hay = normalize(page_text)
        ratio, offset, exact = _best_match(hay, needle)
        if exact or ratio > best_ratio:
            best_ratio, best_page, best_offset, best_exact = ratio, page_no, offset, exact

    ev.match_ratio = round(best_ratio, 4)
    ev.page = best_page
    if best_exact:
        ev.level = EvidenceLevel.A
        ev.char_start = best_offset
        ev.char_end = best_offset + len(needle) if best_offset is not None else None
        ev.note = f"全文第 {best_page} 页逐字命中"
    elif best_ratio >= FUZZY_THRESHOLD:
        ev.level = EvidenceLevel.B
        ev.char_start = best_offset
        ev.char_end = best_offset + len(needle) if best_offset is not None else None
        ev.note = f"第 {best_page} 页近似命中（覆盖度 {best_ratio:.3f}），需人工复核"
    else:
        ev.level = EvidenceLevel.C if ev.quote else EvidenceLevel.D
        ev.note = f"全文未定位到该引句（最高覆盖度 {best_ratio:.2f}）"
    return ev


def ccr(claims) -> tuple[float, int, int]:
    """Citation check rate: verified claims / total claims."""
    total = len(claims)
    if total == 0:
        return 0.0, 0, 0
    ok = sum(1 for c in claims if c.evidence and c.evidence.level in (EvidenceLevel.A, EvidenceLevel.B))
    return round(ok / total, 3), ok, total
