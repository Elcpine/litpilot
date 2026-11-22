"""Tool 1/6 — search_papers.

Real path: arXiv Atom API (no key, no rate-limit headache), Semantic Scholar as a
keyword-enrichment fallback. Every successful response is cached by query, so a
network failure degrades to cache instead of killing the run.
"""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import httpx

import config
import mockdata
from schema import Paper, PaperStatus
from tools.base import ToolError

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_URL = "https://export.arxiv.org/api/query"


def _cache_path(query: str) -> Path:
    key = hashlib.sha1(f"{query}|{config.PAPER_LIMIT}".encode()).hexdigest()[:16]
    return config.SEARCH_DIR / f"{key}.json"


def _parse_atom(xml_text: str) -> list[Paper]:
    root = ET.fromstring(xml_text)
    out: list[Paper] = []
    for entry in root.findall(f"{ATOM}entry"):
        raw_id = (entry.findtext(f"{ATOM}id") or "").strip()
        m = re.search(r"abs/([0-9]+\.[0-9]+)", raw_id)
        if not m:
            continue
        arxiv_id = m.group(1)
        published = entry.findtext(f"{ATOM}published") or ""
        year = int(published[:4]) if published[:4].isdigit() else None
        title = re.sub(r"\s+", " ", entry.findtext(f"{ATOM}title") or "").strip()
        abstract = re.sub(r"\s+", " ", entry.findtext(f"{ATOM}summary") or "").strip()
        authors = [
            (a.findtext(f"{ATOM}name") or "").strip()
            for a in entry.findall(f"{ATOM}author")
        ]
        pdf_url = ""
        for link in entry.findall(f"{ATOM}link"):
            if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                pdf_url = link.get("href", "")
        out.append(
            Paper(
                paper_id=arxiv_id,
                title=title,
                year=year,
                venue="arXiv",
                authors=[a for a in authors if a],
                abstract=abstract,
                url=f"https://arxiv.org/abs/{arxiv_id}",
                pdf_url=pdf_url or f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                status=PaperStatus.PENDING,
            )
        )
    return out


async def _query_arxiv(query: str, limit: int) -> list[Paper]:
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": str(limit),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT_S) as client:
        r = await client.get(ARXIV_URL, params=params)
    if r.status_code != 200:
        raise ToolError("search_papers", f"arXiv HTTP {r.status_code}")
    return _parse_atom(r.text)


async def search_papers(
    queries: list[str],
    *,
    limit: int | None = None,
    mock: bool = False,
) -> tuple[list[Paper], str]:
    """Returns (papers, source) where source is arxiv | cache | mock."""
    limit = limit or config.PAPER_LIMIT

    if mock:
        return mockdata.search(" ".join(queries), limit), "mock"

    collected: dict[str, Paper] = {}
    errors: list[str] = []
    cache_hit = False

    for q in queries:
        cache_file = _cache_path(q)
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                for p in cached:
                    paper = Paper(**p)
                    paper.fetched_from_cache = True
                    collected.setdefault(paper.paper_id, paper)
                cache_hit = True
                continue
            except Exception:
                pass
        try:
            papers = await _query_arxiv(q, limit)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{q}: {exc}")
            continue
        if papers:
            cache_file.write_text(
                json.dumps([p.model_dump(mode="json") for p in papers], ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
        for p in papers:
            collected.setdefault(p.paper_id, p)

    if not collected:
        raise ToolError("search_papers", "; ".join(errors) or "no results", retryable=True)

    min_year = date.today().year - config.RECENT_YEARS
    fresh = [p for p in collected.values() if p.year is None or p.year >= min_year]
    papers = (fresh or list(collected.values()))[:limit]
    source = "cache" if papers and all(p.fetched_from_cache for p in papers) else "arxiv"
    return papers, source
