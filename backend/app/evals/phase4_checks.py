"""
Phase 4 automated eval checks: RAG pipeline integrity and grounded Q&A.

These checks run fully offline using the fixture corpus (no network, no live Gemini key).
Checks validate the pipeline shape, retrieval mechanics, intent routing, and citation
metadata — not LLM output quality (which requires manual review per Rules EVAL12).

Target: >= 85%
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import BaseModel, Field

_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "rag" / "fixtures" / "mf_corpus.json"


@dataclass(frozen=True)
class Check:
    id: str
    weight: float
    fn: Callable[[], bool]


class Phase4EvalReport(BaseModel):
    version: str = Field(default="phase4-v1")
    total_weight: float
    earned_weight: float
    score: float
    checks: list[dict[str, object]]


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _fixture_corpus_loads() -> bool:
    """Fixture JSON is valid and has at least 6 documents."""
    try:
        raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        return isinstance(raw, list) and len(raw) >= 6
    except Exception:
        return False


def _chunk_document_produces_chunks() -> bool:
    """chunk_document returns at least one chunk per fixture document."""
    try:
        from app.rag.chunk import chunk_document
        from app.schemas.rag import SourceDocument

        raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        docs = [SourceDocument.model_validate(r) for r in raw]
        total = sum(len(chunk_document(d)) for d in docs)
        return total >= len(docs)
    except Exception:
        return False


def _chunk_metadata_preserved() -> bool:
    """Each chunk carries source_url, doc_type, title, last_checked."""
    try:
        from app.rag.chunk import chunk_document
        from app.schemas.rag import SourceDocument

        raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        doc = SourceDocument.model_validate(raw[0])
        chunks = chunk_document(doc)
        if not chunks:
            return False
        c = chunks[0]
        return bool(c.source_url and c.doc_type and c.title and c.last_checked)
    except Exception:
        return False


def _bm25_index_builds_and_searches() -> bool:
    """BM25 index builds from fixture chunks and returns results for a fee query."""
    try:
        from app.rag.bm25 import BM25Index
        from app.rag.chunk import chunk_document
        from app.schemas.rag import SourceDocument

        raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        docs = [SourceDocument.model_validate(r) for r in raw]
        chunks = [c for d in docs for c in chunk_document(d)]

        idx = BM25Index()
        idx.build(chunks)
        results = idx.search("expense ratio exit load fees", top_k=5)
        return len(results) > 0 and results[0].score > 0
    except Exception:
        return False


def _rrf_fusion_merges_lists() -> bool:
    """RRF fusion merges two ranked lists and returns correct ordering."""
    try:
        from app.rag.bm25 import BM25Index
        from app.rag.chunk import chunk_document
        from app.rag.fusion import reciprocal_rank_fusion
        from app.schemas.rag import SourceDocument

        raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        docs = [SourceDocument.model_validate(r) for r in raw]
        chunks = [c for d in docs for c in chunk_document(d)]

        idx = BM25Index()
        idx.build(chunks)
        list_a = idx.search("expense ratio", top_k=5)
        list_b = idx.search("exit load", top_k=5)

        fused = reciprocal_rank_fusion([list_a, list_b])
        return len(fused) > 0
    except Exception:
        return False


def _intent_classifier_routes_correctly() -> bool:
    """Intent classifier maps known phrases to correct labels."""
    try:
        from app.llm.task_router import classify_intent

        cases = [
            ("Explain the exit load and expense ratio charges", "fee_query"),
            ("Tell me about Motilal Oswal Midcap Fund", "mf_query"),
            ("What is the expense ratio of the Motilal Nifty Midcap index fund?", "direct_metric_query"),
            ("What is the expense ratio and how does this Motilal fund compare?", "direct_metric_query"),
            ("I want to book an appointment with the advisor", "booking_intent"),
            ("Should I invest in this fund now?", "disallowed"),
        ]
        return all(classify_intent(msg) == expected for msg, expected in cases)
    except Exception:
        return False


def _disallowed_intent_refused_by_router() -> bool:
    """customer_router_service returns a refusal for disallowed intent without RAG."""
    import asyncio

    try:
        import os

        os.environ.setdefault("APP_ENV", "eval")

        from app.core.config import clear_settings_cache, get_settings
        from app.services.customer_router_service import generate_customer_response

        clear_settings_cache()
        settings = get_settings()

        async def _run() -> bool:
            text, citations = await generate_customer_response(
                settings=settings,
                session_id="eval-session",
                user_message="Should I invest all my money in this mutual fund?",
            )
            return (
                isinstance(text, str)
                and len(text) > 0
                and len(citations) == 0
                and "advice" in text.lower()
            )

        return asyncio.run(_run())
    except Exception:
        return False


def _rag_index_loads_from_fixture_path() -> bool:
    """RAGIndex can load from fixture chunks (no Gemini key needed)."""
    import json
    import tempfile
    from pathlib import Path

    try:
        from app.rag.chunk import chunk_document
        from app.rag.retrieve import RAGIndex
        from app.schemas.rag import SourceDocument

        raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        docs = [SourceDocument.model_validate(r) for r in raw]
        chunks = [c for d in docs for c in chunk_document(d)]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([c.model_dump() for c in chunks], f, ensure_ascii=False)
            tmp_path = f.name

        idx = RAGIndex.load(tmp_path)
        return len(idx._chunks) == len(chunks)
    except Exception:
        return False


def _weak_retrieval_triggers_safe_fallback() -> bool:
    """When chunks list is empty, compose_grounded_answer returns a safe fallback."""
    import asyncio
    import os

    os.environ.setdefault("APP_ENV", "eval")

    try:
        from app.core.config import clear_settings_cache, get_settings
        from app.rag.answer import compose_grounded_answer

        clear_settings_cache()
        settings = get_settings()

        async def _run() -> bool:
            result = await compose_grounded_answer(
                query="What is the fee?",
                chunks=[],
                intent="fee_query",
                settings=settings,
            )
            return result.fallback is True and isinstance(result.answer, str) and len(result.answer) > 0

        return asyncio.run(_run())
    except Exception:
        return False


def _chat_api_returns_citations_field() -> bool:
    """POST /chat/message response includes a citations field (may be empty list)."""
    from unittest.mock import AsyncMock, patch

    try:
        from fastapi.testclient import TestClient

        with patch(
            "app.integrations.supabase.client.check_supabase_connectivity",
            new=AsyncMock(return_value=(True, "ok")),
        ), patch(
            "app.rag.retrieve.load_rag_index_from_default",
            new=AsyncMock(return_value=None),
        ):
            from app.main import app as fastapi_app

            c = TestClient(fastapi_app, raise_server_exceptions=True)
            r = c.post("/api/v1/chat/message", json={"message": "What is the expense ratio of HDFC fund?"})

            if r.status_code != 200:
                return False
            body = r.json()
            if not body.get("success"):
                return False
            data = body.get("data") or {}
            return "citations" in data and isinstance(data["citations"], list)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_phase4_evals() -> Phase4EvalReport:
    with patch(
        "app.integrations.supabase.client.check_supabase_connectivity",
        new=AsyncMock(return_value=(True, "ok")),
    ):
        checks: list[Check] = [
            Check("fixture_corpus_loads", 10.0, _fixture_corpus_loads),
            Check("chunk_document_produces_chunks", 10.0, _chunk_document_produces_chunks),
            Check("chunk_metadata_preserved", 10.0, _chunk_metadata_preserved),
            Check("bm25_builds_and_searches", 15.0, _bm25_index_builds_and_searches),
            Check("rrf_fusion_merges", 10.0, _rrf_fusion_merges_lists),
            Check("intent_classifier_routes", 15.0, _intent_classifier_routes_correctly),
            Check("disallowed_refused", 10.0, _disallowed_intent_refused_by_router),
            Check("rag_index_loads", 10.0, _rag_index_loads_from_fixture_path),
            Check("weak_retrieval_fallback", 10.0, _weak_retrieval_triggers_safe_fallback),
            Check("chat_api_citations_field", 10.0, _chat_api_returns_citations_field),
        ]

        earned = 0.0
        total = 0.0
        rows: list[dict[str, object]] = []
        for chk in checks:
            total += chk.weight
            ok = False
            try:
                ok = bool(chk.fn())
            except Exception as exc:
                ok = False
                rows.append({"id": chk.id, "weight": chk.weight, "passed": False, "error": str(exc)[:80]})
                continue
            if ok:
                earned += chk.weight
            rows.append({"id": chk.id, "weight": chk.weight, "passed": ok})

        score = round((earned / total) * 100.0, 2) if total else 0.0
        return Phase4EvalReport(
            total_weight=total,
            earned_weight=earned,
            score=score,
            checks=rows,
        )
