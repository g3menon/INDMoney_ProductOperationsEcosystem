"""RAG pipeline schemas (Phase 4): SourceDocument, DocumentChunk, ScoredChunk,
CitationSource, and structured MF metrics models (MFFundMetrics et al.)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DocType = Literal["mutual_fund_page", "fee_explainer"]

IntentLabel = Literal[
    "mf_query",
    "fee_query",
    "hybrid_query",
    "direct_metric_query",
    "booking_intent",
    "out_of_scope",
    "disallowed",
]


class SourceDocument(BaseModel):
    doc_id: str
    url: str
    title: str
    doc_type: DocType
    last_checked: str
    content: str
    scraped_at: str | None = None


class DocumentChunk(BaseModel):
    chunk_id: str
    doc_id: str
    source_url: str
    title: str
    doc_type: DocType
    last_checked: str
    content: str
    chunk_index: int = 0
    embedding: list[float] | None = Field(default=None)


class ScoredChunk(BaseModel):
    chunk: DocumentChunk
    score: float = 0.0


class CitationSource(BaseModel):
    source_url: str
    doc_type: str
    title: str
    last_checked: str
    relevant_quote: str | None = None


# ---------------------------------------------------------------------------
# Phase 4 extended: structured mutual-fund metrics
# ---------------------------------------------------------------------------


class MFReturns(BaseModel):
    """Annualised returns across standard durations (% values; 18.5 means 18.5%)."""

    one_month: float | None = None
    three_month: float | None = None
    six_month: float | None = None
    one_year: float | None = None
    three_year: float | None = None
    five_year: float | None = None
    since_inception: float | None = None


class MFHolding(BaseModel):
    name: str
    weight_pct: float | None = None
    sector: str | None = None


class MFSectorAlloc(BaseModel):
    sector: str
    weight_pct: float | None = None


class MFFundMetrics(BaseModel):
    """Structured mutual-fund metrics extracted from a Groww MF page.

    Fields that cannot be extracted without JavaScript rendering are None.
    Inspect the accompanying ExtractionReport for per-field availability.
    """

    doc_id: str
    fund_name: str
    amc: str | None = None
    category: str | None = None
    sub_category: str | None = None
    plan: str | None = None              # "Direct" | "Regular"
    option: str | None = None            # "Growth" | "IDCW"
    nav: float | None = None
    nav_date: str | None = None
    aum_cr: float | None = None          # AUM in crores
    expense_ratio_pct: float | None = None
    exit_load_pct: float | None = None
    exit_load_window_days: int | None = None
    exit_load_description: str | None = None
    risk_level: str | None = None
    rating: str | None = None
    benchmark: str | None = None
    min_sip_amount: float | None = None
    min_lumpsum_amount: float | None = None
    returns: MFReturns | None = None
    top_holdings: list[MFHolding] = Field(default_factory=list)
    sector_allocation: list[MFSectorAlloc] = Field(default_factory=list)
    asset_allocation: dict[str, float] = Field(default_factory=dict)
    fund_objective: str | None = None
    source_url: str
    scraped_at: str
    last_checked: str
