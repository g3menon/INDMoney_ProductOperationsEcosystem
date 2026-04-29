"""RAG pipeline schemas (Phase 4): DocumentChunk, ScoredChunk, CitationSource."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DocType = Literal["mutual_fund_page", "fee_explainer"]

IntentLabel = Literal[
    "mf_query",
    "fee_query",
    "hybrid_query",
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
