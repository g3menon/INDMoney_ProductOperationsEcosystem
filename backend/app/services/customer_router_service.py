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
5. mutual_fund_info_query / fee_query → hybrid RAG retrieval → grounded answer.
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

from app.llm.task_router import DISALLOWED_RESPONSES, assign_model_tier, classify_intent
from app.rag.answer import (
    AnswerResult,
    compose_grounded_answer,
    compose_hybrid_answer,
    compose_structured_answer,
)
from app.rag.metrics_store import get_metrics_store
from app.rag.retrieve import get_rag_index
from app.schemas.rag import CitationSource, MFFundMetrics
from app.services.pulse_theme_cache import get_active_themes

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

_DISCLAIMER = "This is general information only, not personalised financial advice."

_BOOKING_RESPONSE = (
    "To book an advisor appointment, please share: (1) your preferred date/time window, "
    "(2) your mutual fund or fee question or goal, and (3) your timezone (we default to IST). "
    f"I will help you proceed with the booking flow. {_DISCLAIMER}"
)

def _build_booking_greeting(themes: list) -> str:
    """Build a theme-aware greeting for booking_intent.
    Falls back to static _BOOKING_RESPONSE if no themes are available."""
    if not themes:
        return _BOOKING_RESPONSE
    top_theme = getattr(themes[0], "theme", None)
    if not top_theme:
        return _BOOKING_RESPONSE
    return (
        f"I can help you book a call with a Groww advisor. "
        f"I noticed many users are currently asking about {top_theme} — "
        f"I can make sure your advisor is briefed on this when you connect. "
        f"What topic would you like to discuss, and when are you available? "
        f"{_DISCLAIMER}"
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
    if any(k in lower for k in ["review", "reviews", "complaint", "feedback",
                                 "user feedback", "play store", "playstore",
                                 "rating", "1 star", "2 star"]):
        return (
            "I can help analyse Play Store reviews and user feedback. "
            "The review index is currently being loaded — please try again in a moment. "
            f"{_DISCLAIMER}"
        )
    if any(k in lower for k in ["trend", "trending", "rising", "spike",
                                 "more than last", "compared to", "month on month"]):
        return (
            "I can help with trend analysis across review periods. "
            "The review index is currently loading — please try again shortly. "
            f"{_DISCLAIMER}"
        )
    if any(k in lower for k in ["why", "root cause", "crash", "regression",
                                 "what changed", "version", "after update"]):
        return (
            "I can help diagnose product issues from review data and version history. "
            "The review index is loading — please try again in a moment. "
            f"{_DISCLAIMER}"
        )
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


def _is_nav_metric_query(user_message: str) -> bool:
    lower = user_message.lower()
    return "nav" in lower or "net asset value" in lower or "current nav" in lower


async def _try_live_nav_enrichment(
    metrics: MFFundMetrics,
) -> tuple[MFFundMetrics, CitationSource | None]:
    """Best-effort HTTP-only NAV enrichment for direct NAV lookups."""
    if metrics.nav is not None:
        return metrics, None
    try:
        from app.integrations.mf_nav_provider import lookup_latest_nav

        nav_result = await lookup_latest_nav(metrics.fund_name)
    except Exception as exc:
        logger.warning(
            "customer_router_nav_enrichment_error",
            extra={"doc_id": metrics.doc_id, "error": str(exc)[:160]},
        )
        return metrics, None
    if nav_result is None:
        return metrics, None

    enriched = metrics.model_copy(
        update={
            "nav": nav_result.nav,
            "nav_date": nav_result.nav_date,
            "nav_source_url": nav_result.source_url,
        }
    )
    citation = CitationSource(
        source_url=nav_result.source_url,
        doc_type="mutual_fund_nav",
        title=f"AMFI latest NAV - {nav_result.scheme_name}",
        last_checked=nav_result.nav_date,
    )
    return enriched, citation


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def generate_customer_response(
    settings: "Settings",
    session_id: str,
    user_message: str,
) -> tuple[str, list[CitationSource]]:
    """Return (assistant_text, citations) for the given user message."""
    text, citations, _metadata = await _generate_customer_response(
        settings=settings,
        session_id=session_id,
        user_message=user_message,
    )
    return text, citations


async def generate_customer_response_with_metadata(
    settings: "Settings",
    session_id: str,
    user_message: str,
) -> tuple[str, list[CitationSource], dict[str, object]]:
    """Return assistant text, citations, and observability metadata."""
    return await _generate_customer_response(
        settings=settings,
        session_id=session_id,
        user_message=user_message,
    )


async def _generate_customer_response(
    settings: "Settings",
    session_id: str,
    user_message: str,
) -> tuple[str, list[CitationSource], dict[str, object]]:
    t0 = time.monotonic()
    intent = classify_intent(user_message)
    lower = user_message.lower()
    metadata = _base_metadata(intent=intent)

    logger.info(
        "customer_router_intent",
        extra={
            "session_id": session_id,
            "intent": intent,
            "model_tier": metadata["model_tier"],
            "msg_len": len(user_message),
        },
    )

    # ── 1. Disallowed / out-of-scope ─────────────────────────────────────
    if intent in DISALLOWED_RESPONSES:
        metadata.update({"fallback_used": True, "fallback_reason": intent})
        logger.warning(
            "fallback_triggered",
            extra={"session_id": session_id, "fallback": "policy_response", "reason": intent},
        )
        return DISALLOWED_RESPONSES[intent], [], metadata

    # ── 2. Booking intent ────────────────────────────────────────────────
    if intent == "booking_intent":
        try:
            import asyncio
            themes = await asyncio.wait_for(
                asyncio.to_thread(get_active_themes, settings),
                timeout=0.5,
            )
        except Exception:
            themes = []
        greeting = _build_booking_greeting(themes)
        logger.info(
            "booking_greeting_enriched",
            extra={
                "session_id": session_id,
                "theme_used": getattr(themes[0], "theme", "none") if themes else "none",
                "themes_available": len(themes),
            },
        )
        return greeting, [], metadata

    # ── 2.5 Clarify ambiguous metric questions (metric asked, fund missing) ──
    # Example: "What is the expense ratio?" should ask WHICH fund; whereas
    # "What is an expense ratio?" should explain the concept via RAG.
    if intent in ("fee_query",) and any(k in lower for k in ("expense ratio", "exit load", "ter")):
        if " an " not in lower and not any(f in lower for f in ("hdfc", "motilal", "midcap", "flexi", "index", "fund")):
            return _CLARIFY_FUND, [], metadata

    # ── 3. direct_metric_query ───────────────────────────────────────────
    if intent == "direct_metric_query":
        # GUARDRAIL: direct_metric_query never calls Gemini or Groq.
        # Response is assembled from MFMetricsStore, with HTTP-only AMFI NAV
        # enrichment for direct NAV lookups when the indexed snapshot is empty.
        metrics = _try_metrics_lookup(user_message)
        if metrics is None:
            # Fund not identifiable → ask for clarification.
            logger.info(
                "customer_router_direct_metric_no_match",
                extra={"session_id": session_id},
            )
            return _CLARIFY_FUND, [], metadata
        nav_citation: CitationSource | None = None
        is_nav_query = _is_nav_metric_query(user_message)
        if is_nav_query:
            metrics, nav_citation = await _try_live_nav_enrichment(metrics)
            metadata["nav_enriched"] = nav_citation is not None
        from app.llm.response_cache import (
            get_cached,
            log_cache_hit,
            log_cache_miss,
            make_cache_key,
            set_cached,
            should_bypass_cache,
        )

        cache_key = make_cache_key(intent=intent, query=user_message, fund_doc_id=metrics.doc_id)
        if not is_nav_query and not should_bypass_cache(settings, user_message):
            cached = get_cached(cache_key)
            if cached:
                log_cache_hit(intent, cache_key)
                # Citations are deterministic for structured answers.
                result = compose_structured_answer(user_message, metrics, intent)
                metadata = _with_answer_metadata(metadata, result)
                return cached, result.citations, metadata
            log_cache_miss(intent)

        result = compose_structured_answer(user_message, metrics, intent)
        if nav_citation and all(c.source_url != nav_citation.source_url for c in result.citations):
            result.citations.append(nav_citation)
        if not is_nav_query and not should_bypass_cache(settings, user_message):
            set_cached(cache_key, result.answer, ttl=3600)
        _log_done(session_id, intent, result, t0)
        metadata = _with_answer_metadata(metadata, result)
        return result.answer, result.citations, metadata

    # ── 4. RAG path ──────────────────────────────────────────────────────
    rag_index = get_rag_index()
    if rag_index is None:
        logger.warning(
            "rag_index_not_loaded_using_phase3_fallback",
            extra={"session_id": session_id},
        )
        metadata.update({"fallback_used": True, "fallback_reason": "rag_index_missing"})
        logger.warning(
            "fallback_triggered",
            extra={"session_id": session_id, "fallback": "phase3_response", "reason": "rag_index_missing"},
        )
        return _phase3_fallback(user_message), [], metadata

    metadata["rag_index_available"] = True
    retrieval = await rag_index.search_with_metadata(
        query=user_message,
        settings=settings,
        top_k=5,
        use_rerank=False,
    )
    chunks = retrieval.chunks
    metadata.update(
        {
            "rag_chunks_retrieved": len(chunks),
            "retrieval_mode": retrieval.retrieval_mode,
            "retrieval_stats": {
                "bm25_hits": retrieval.bm25_hits,
                "embedding_hits": retrieval.embedding_hits,
                "fused_hits": retrieval.fused_hits,
                "retrieval_mode": retrieval.retrieval_mode,
            },
        }
    )
    logger.info(
        "customer_router_retrieval_completed",
        extra={
            "session_id": session_id,
            "intent": intent,
            "rag_chunks_retrieved": len(chunks),
            "retrieval_mode": retrieval.retrieval_mode,
        },
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
            metadata = _with_answer_metadata(metadata, result)
            return result.answer, result.citations, metadata
        # No fund match → fall through to standard RAG answer below.

    # ── 6. mutual_fund_info_query / fee_query / product_review_query /
    #       trend_query / issue_diagnosis_query / unmatched hybrid → grounded RAG ──
    result = await compose_grounded_answer(
        query=user_message,
        chunks=chunks,
        intent=intent,
        settings=settings,
    )

    _log_done(session_id, intent, result, t0)
    metadata = _with_answer_metadata(metadata, result)
    return result.answer, result.citations, metadata


def _base_metadata(intent: str) -> dict[str, object]:
    tier = assign_model_tier(intent)  # light routes are deterministic but exposed as standard.
    return {
        "intent": intent,
        "model_tier": "heavy" if tier == "heavy" else "standard",
        "provider_used": "none",
        "model_used": None,
        "fallback_used": False,
        "fallback_reason": None,
        "rag_index_available": get_rag_index() is not None,
        "rag_chunks_retrieved": 0,
        "rag_chunks_sent_to_llm": 0,
        "retrieval_mode": "none",
        "retrieval_stats": {
            "bm25_hits": 0,
            "embedding_hits": 0,
            "fused_hits": 0,
            "retrieval_mode": "none",
        },
    }


def _with_answer_metadata(base: dict[str, object], result: AnswerResult) -> dict[str, object]:
    metadata = dict(base)
    result_metadata = result.metadata or {}
    metadata.update(
        {
            "provider_used": result_metadata.get("provider_used", "none"),
            "model_used": result_metadata.get("model_used"),
            "fallback_used": bool(result_metadata.get("fallback_used", result.fallback)),
            "fallback_reason": result_metadata.get("fallback_reason", result.fallback_reason),
            "rag_chunks_sent_to_llm": int(result_metadata.get("rag_chunks_sent_to_llm", 0) or 0),
        }
    )
    return metadata


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
