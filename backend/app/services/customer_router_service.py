"""Customer routing service (Phase 4: RAG-backed grounded answers).

Pipeline (Rules P4.1-P4.8, R1-R6, R13):
1. classify_intent → short-circuit disallowed / out_of_scope early (R13).
2. booking_intent → direct booking response (Phase 5 wiring point).
3. mf_query / fee_query / hybrid_query → hybrid RAG retrieval → grounded answer.
4. Weak retrieval (no hits) → safe fallback (R1, P4.3).

Returns (assistant_text, citations) so the API layer can carry citations to
the frontend for rendering (Rules R12, P4.7).

Backward compatibility:
- If the RAG index is not loaded (index file absent), falls back to the Phase 3
  deterministic skeleton and logs a warning. This keeps the chat runtime stable
  while the index is being built (Rules G7).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from app.llm.task_router import DISALLOWED_RESPONSES, classify_intent
from app.rag.answer import AnswerResult, compose_grounded_answer
from app.rag.retrieve import get_rag_index
from app.schemas.rag import CitationSource

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

_DISCLAIMER = "General information only, not financial advice."

_BOOKING_RESPONSE = (
    "To book an advisor appointment, please share: (1) your preferred date/time window, "
    "(2) your mutual fund or fee question or goal, and (3) your timezone (we default to IST). "
    f"I will help you proceed with the booking flow. {_DISCLAIMER}"
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
# Main entry point
# ---------------------------------------------------------------------------


async def generate_customer_response(
    settings: "Settings",
    session_id: str,
    user_message: str,
) -> tuple[str, list[CitationSource]]:
    """Return (assistant_text, citations) for the given user message.

    Citations list is empty for non-RAG responses (booking, fallback, refusals).
    """
    t0 = time.monotonic()
    intent = classify_intent(user_message)

    logger.info(
        "customer_router_intent",
        extra={"session_id": session_id, "intent": intent, "msg_len": len(user_message)},
    )

    # ── 1. Disallowed / out-of-scope: refuse early (Rules R13) ──────────────
    if intent in DISALLOWED_RESPONSES:
        msg = DISALLOWED_RESPONSES[intent]
        return msg, []

    # ── 2. Booking intent ────────────────────────────────────────────────────
    if intent == "booking_intent":
        return _BOOKING_RESPONSE, []

    # ── 3. RAG path ──────────────────────────────────────────────────────────
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

    result: AnswerResult = await compose_grounded_answer(
        query=user_message,
        chunks=chunks,
        intent=intent,
        settings=settings,
    )

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

    return result.answer, result.citations
