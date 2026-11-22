"""Tool 2/6 — fetch_pdf.

Downloads the PDF into the local cache. A failure here is not fatal: the paper
degrades to ``summary_only`` and the critic is expected to catch it later. That
degradation path is the point of the demo, so never swallow the reason.

``fault=True`` simulates the network timeout that the design document’s demo
walks through (third paper). It is a demo switch, not a test hack: the retry that
follows is real code.
"""

from __future__ import annotations

import httpx

import config
import mockdata
from schema import Paper, PaperStatus
from tools.base import ToolError

MIN_PDF_BYTES = 20_000


async def fetch_pdf(paper: Paper, *, mock: bool = False, fault: bool = False) -> Paper:
    if fault:
        raise ToolError("fetch_pdf", f"下载超时（超过 {config.FETCH_TIMEOUT_S:.0f}s 上限）")

    if mock:
        paper.status = PaperStatus.FETCHED
        paper.pdf_path = None
        return paper

    dest = config.PDF_DIR / f"{paper.paper_id}.pdf"
    if dest.exists() and dest.stat().st_size >= MIN_PDF_BYTES:
        paper.pdf_path = str(dest)
        paper.status = PaperStatus.FETCHED
        paper.fetched_from_cache = True
        return paper

    if not paper.pdf_url:
        raise ToolError("fetch_pdf", "没有 pdf_url", retryable=False)

    try:
        async with httpx.AsyncClient(
            timeout=config.FETCH_TIMEOUT_S, follow_redirects=True
        ) as client:
            r = await client.get(paper.pdf_url)
    except httpx.TimeoutException as exc:
        raise ToolError("fetch_pdf", f"下载超时：{exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ToolError("fetch_pdf", f"下载失败：{exc}") from exc

    if r.status_code != 200:
        raise ToolError("fetch_pdf", f"HTTP {r.status_code}")
    body = r.content
    if len(body) < MIN_PDF_BYTES:
        raise ToolError("fetch_pdf", f"文件过小（{len(body)}B），可能不是 PDF")
    if not body.startswith(b"%PDF"):
        raise ToolError("fetch_pdf", "返回内容不是 PDF")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    paper.pdf_path = str(dest)
    paper.status = PaperStatus.FETCHED
    return paper


def cache_summary() -> dict:
    """For the UI footer: what is already on disk."""
    if not config.PDF_DIR.exists():
        return {"pdfs": 0, "mb": 0.0}
    files = list(config.PDF_DIR.glob("*.pdf"))
    return {
        "pdfs": len(files),
        "mb": round(sum(f.stat().st_size for f in files) / 1e6, 1),
        "mock_papers": len(mockdata.PAPERS),
    }
