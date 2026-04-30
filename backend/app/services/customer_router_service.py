"""Customer routing service (Phase 4: RAG-backed grounded answers).

Pipeline (Rules P4.1-P4.8, R1-R6, R13):
1. classify_intent → short-circuit disallowed / out_of_scope early (R13).
2. booking_intent → direct booking response (Phase 5 wiring point).
3. direct_metric_query → try structured metrics lookup first:
     - fund matched → compose_structured_answer (deterministic, no LLM)
     - fund not matched → ask clarifying question
4. hybrid_query → try structured metrics lookup:
     - fund matched → compose_hybrid_answer (metrics + RAG chunks → Gemini)
     - fund not matched → RAG-only path
5. mf_query / fee_query → hybrid RAG retrieval → grounded answer.
6. Weak retrieval (no hits) → safe fallback (R1, P4.3).

Returns (assistant_text, citations) so the API layer can carry citations to
the frontend for rendering (Rules R12, P4.7).

Backward compatibility:
- If RAG index absent → falls back to Phase 3 deterministic skeleton.
- If metrics store absent → direct_metric_query / hybrid_query degrade to RAG-only.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from app.llm.task_router import DISALLOWED_RESPONSES, classify_intent
from app.rag.answer import (
    AnswerResult,
    compose_grounded_answer,
    compose_hybrid_answer,
    compose_structured_answer,
)
from app.rag.metrics_store import get_metrics_store
from app.rag.retrieve import get_rag_index
from app.schemas.rag import CitationSource, MFFundMetrics

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

_DISCLAIMER = "This is general information only, not personalised financial advice."

_BOOKING_RESPONSE = (
    "To book an advisor appointment, please share: (1) your preferred date/time window, "
    "(2) your mutual fund or fee question or goal, and (3) your timezone (we default to IST). "
    f"I will help you proceed with the booking flow. {_DISCLAIMER}"
)

_CLARIFY_FUND = (
    "I can look up that metric directly. Could you tell me which mutual fund you are "
    "asking about? For example: 'What is the expense ratio of HDFC Large Cap Fund?' "
    f"{_DISCLAIMER}"
)


# ---------------------------------------------------------------------------
# Phase 3 deterministic skeleton (fallback when RAG index is absent)
# ---------------------------------------------------------------------------


def _phase3_fallback(user_message: str) -> str:
    lower = user_message.lower()
    if any(k in lower for k in ["expense ratio", "exit load", "fees", "fee", "expense", "load"]):
        return (
            "Mutual fund fees include the expense ratio and sometimes an exit load. "
            "If you share which fund you are looking at, I can explain what the fee means in plain terms. "
            f"{_DISCLAIMER}"
        )
    if any(k in lower for k in ["mutual fund", "sip", "index fund", "fund"]):
        return (
            "A mutual fund pools money from many investors and invests it based on the fund's objective. "
            "Share what you want to achieve (growth, stability, timeframe) and I can explain relevant fund characteristics. "
            f"{_DISCLAIMER}"
        )
    if any(k in lower for k in ["book", "booking", "advisor", "appointment", "schedule", "slot"]):
        return _BOOKING_RESPONSE
    return (
        "I can help with mutual fund questions or fee/expense explanations. "
        f"What are you looking for—mutual fund basics, or fees/expense ratio? {_DISCLAIMER}"
    )


# ---------------------------------------------------------------------------
# Structured metrics lookup helper
# ---------------------------------------------------------------------------


def _try_metrics_lookup(user_message: str) -> MFFundMetrics | None:
    """Try to find a matching fund in the metrics store for the given query."""
    store = get_metrics_store()
    if store is None:
        return None
    return store.find_closest_match(user_message)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def generate_customer_response(
    settings: "Settings",
    session_id: str,
    user_message: str,
) -> tuple[str, list[CitationSource]]:
    """Return (assistant_text, citations) for the given user message."""
    t0 = time.monotonic()
    intent = classify_intent(user_message)
    lower = user_message.lower()

    logger.info(
        "customer_router_intent",
        extra={"session_id": session_id, "intent": intent, "msg_len": len(user_message)},
    )

    # ── 1. Disallowed / out-of-scope ─────────────────────────────────────
    if intent in DISALLOWED_RESPONSES:
        return DISALLOWED_RESPONSES[intent], []

    # ── 2. Booking intent ────────────────────────────────────────────────
    if intent == "booking_intent":
        return _BOOKING_RESPONSE, []

    # ── 2.5 Clarify ambiguous metric questions (metric asked, fund missing) ──
    # Example: "What is the expense ratio?" should ask WHICH fund; whereas
    # "What is an expense ratio?" should explain the concept via RAG.
    if intent in ("fee_query",) and any(k in lower for k in ("expense ratio", "exit load", "ter")):
        if " an " not in lower and not any(f in lower for f in ("hdfc", "motilal", "midcap", "flexi", "index", "fund")):
            return _CLARIFY_FUND, []

    # ── 3. direct_metric_query ───────────────────────────────────────────
    if intent == "direct_metric_query":
        # GUARDRAIL: direct_metric_query never calls Gemini or Groq.
        # Response is assembled from MFMetricsStore only.
        metrics = _try_metrics_lookup(user_message)
        if metrics is None:
            # Fund not identifiable → ask for clarification.
            logger.info(
                "customer_router_direct_metric_no_match",
                extra={"session_id": session_id},
            )
            return _CLARIFY_FUND, []
        from app.llm.response_cache import (
            get_cached,
            log_cache_hit,
            log_cache_miss,
            make_cache_key,
            set_cached,
            should_bypass_cache,
        )

        cache_key = make_cache_key(intent=intent, query=user_message, fund_doc_id=metrics.doc_id)
        if not should_bypass_cache(settings, user_message):
            cached = get_cached(cache_key)
            if cached:
                log_cache_hit(intent, cache_key)
                # Citations are deterministic for structured answers.
                result = compose_structured_answer(user_message, metrics, intent)
                return cached, result.citations
            log_cache_miss(intent)

        result = compose_structured_answer(user_message, metrics, intent)
        if not should_bypass_cache(settings, user_message):
            set_cached(cache_key, result.answer, ttl=3600)
        _log_done(session_id, intent, result, t0)
        return result.answer, result.citations

    # ── 4. RAG path ──────────────────────────────────────────────────────
    rag_index = get_rag_index()
    if rag_index is None:
        logger.warning(
            "rag_index_not_loaded_using_phase3_fallback",
            extra={"session_id": session_id},
        )
        return _phase3_fallback(user_message), []

    chunks = await rag_index.search(
        query=user_message,
        settings=settings,
        top_k=5,
        use_rerank=False,
    )

    # ── 5. hybrid_query: try metrics + RAG together ───────────────────────
    if intent == "hybrid_query":
        metrics = _try_metrics_lookup(user_message)
        if metrics is not None:
            result = await compose_hybrid_answer(
                query=user_message,
                metrics=metrics,
                chunks=chunks,
                intent=intent,
                settings=settings,
            )
            _log_done(session_id, intent, result, t0)
            return result.answer, result.citations
        # No fund match → fall through to standard RAG answer below.

    # ── 6. mf_query / fee_query / unmatched hybrid → grounded RAG ────────
    result = await compose_grounded_answer(
        query=user_message,
        chunks=chunks,
        intent=intent,
        settings=settings,
    )

    _log_done(session_id, intent, result, t0)
    return result.answer, result.citations


def _log_done(
    session_id: str,
    intent: str,
    result: AnswerResult,
    t0: float,
) -> None:
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "customer_router_done",
        extra={
            "session_id": session_id,
            "intent": intent,
            "citations": len(result.citations),
            "fallback": result.fallback,
            "elapsed_ms": elapsed_ms,
        },
    )
