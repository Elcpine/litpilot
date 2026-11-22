"""Frozen data contracts.

Every module exchanges only these shapes. This file is the coordination point:
once it stops changing, backend / frontend / docs can work in parallel.
If you need a new field, add it here first, then implement it.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PaperStatus(str, Enum):
    PENDING = "pending"
    FETCHED = "fetched"          # full text available
    PARSE_FAILED = "parse_failed"  # downloaded but text extraction failed
    SUMMARY_ONLY = "summary_only"  # download failed -> abstract only


class EvidenceLevel(str, Enum):
    """A > B > C > D. This ladder is the product's core claim."""

    A = "A"  # quote found verbatim in full text (after normalization)
    B = "B"  # fuzzy match, same paragraph, ratio >= 0.95
    C = "C"  # abstract only / could not be located
    D = "D"  # no source at all -> never used in conclusions


ELIGIBLE_LEVELS = {EvidenceLevel.A, EvidenceLevel.B}


class Paper(BaseModel):
    paper_id: str
    title: str
    year: int | None = None
    venue: str | None = None
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    url: str = ""
    pdf_url: str = ""
    pdf_path: str | None = None
    status: PaperStatus = PaperStatus.PENDING
    fetched_from_cache: bool = False


class Metric(BaseModel):
    name: str
    value: str


class ExtractedField(BaseModel):
    """One row's worth of structured content, plus what it was derived from."""

    paper_id: str
    task: str = ""
    method: str = ""
    dataset: str = ""
    metrics: list[Metric] = Field(default_factory=list)
    baseline: str = ""
    limitation: str = ""
    source: str = "full_text"  # full_text | abstract
    complete: bool = False  # method + dataset + metrics all present


class Evidence(BaseModel):
    evid_id: str
    paper_id: str
    claim_id: str
    quote: str
    level: EvidenceLevel
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    match_ratio: float = 0.0
    note: str = ""


class Claim(BaseModel):
    claim_id: str
    paper_id: str
    text: str
    section: str = ""
    evidence: Evidence | None = None

    @property
    def level(self) -> EvidenceLevel:
        return self.evidence.level if self.evidence else EvidenceLevel.D


class TableRow(BaseModel):
    paper_id: str
    title: str
    year: int | None = None
    method: str = ""
    dataset: str = ""
    metrics: list[Metric] = Field(default_factory=list)
    baseline: str = ""
    worst_level: EvidenceLevel = EvidenceLevel.D
    status: PaperStatus = PaperStatus.PENDING
    source: str = "full_text"
    used_in_conclusion: bool = False
    from_cache: bool = False


class Metrics(BaseModel):
    ccr: float = 0.0               # verified claims / total claims
    claims_total: int = 0
    claims_verified: int = 0
    field_completeness: float = 0.0
    level_dist: dict[str, int] = Field(default_factory=dict)
    extract_retries: int = 0
    failures: int = 0
    failures_visible: int = 0
    papers_total: int = 0
    duration_s: float = 0.0
    # 这一轮花了多少钱。演示时被问"跑一次多少钱"就靠这三个数回答，
    # 别用拍脑袋的估算——LLM 调用次数、token 数、按官方价的美元数都是实测。
    llm_calls: int = 0
    llm_tokens: int = 0
    cost_usd: float = 0.0


class RunResult(BaseModel):
    run_id: str
    topic: str
    mock: bool
    plan: list[dict] = Field(default_factory=list)
    papers: list[Paper] = Field(default_factory=list)
    fields: list[ExtractedField] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    table: list[TableRow] = Field(default_factory=list)
    metrics: Metrics = Field(default_factory=Metrics)
    started_at: str = ""
    finished_at: str = ""


class TraceEvent(BaseModel):
    seq: int
    ts: str
    run_id: str
    node: str          # planner | search | fetch | parse | extract | table | critic | done
    tool: str = ""     # one of the six tool names, when applicable
    status: str = "ok"  # ok | warn | error | retry
    title: str = ""
    detail: dict = Field(default_factory=dict)
    decision: str = ""
