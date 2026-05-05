"""Intent classification for customer chat messages (Phase 4, Rules R13).

Classifies incoming messages into one of the IntentLabels so the
customer_router_service can route correctly:

- direct_metric_query → specific metric (expense ratio, NAV, exit load …) +
                        identifiable fund context → structured metrics lookup
                        (checked first, before fee/mf/hybrid)
- mf_query            → RAG retrieval on mutual fund pages
- fee_query           → RAG retrieval on expense ratio / exit load content
- hybrid_query        → metric keyword AND explanatory/comparative intent together
- booking_intent      → Hand off to booking response (Phase 5+ wiring)
- out_of_scope        → Safe educational fallback
- disallowed          → Refuse early (Rules R13)

Classification is keyword-first (fast, deterministic) to keep latency low (Rules L7).

hybrid_query fires ONLY when both a metric keyword (a) AND an explanatory or
comparative intent keyword (b) are present.  Queries with a fund name but no
metric keyword route to mf_query (standard/Groq) so Gemini quota is not wasted.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from app.schemas.rag import IntentLabel

logger = logging.getLogger(__name__)

# ---- keyword sets ----

_DISALLOWED_PATTERNS = re.compile(
    r"\b(should i invest|will .* go up|predict|guarantee|assured return"
    r"|aadhar|aadhaar|pan card|phone number|bank account|password|otp"
    r"|hack|exploit|bypass|illegal)\b",
    re.I,
)

_BOOKING_KEYWORDS = frozenset(
    ["book", "booking", "appointment", "advisor", "schedule", "slot", "meet", "call with", "speak to"]
)

_FEE_KEYWORDS = frozenset(
    [
        "expense ratio",
        "expense",
        "ter",
        "exit load",
        "fee",
        "fees",
        "charge",
        "charges",
        "cost",
        "costs",
        "commission",
        "direct plan",
        "regular plan",
    ]
)

_MF_KEYWORDS = frozenset(
    [
        "mutual fund",
        "mf",
        "sip",
        "lump sum",
        "lumpsum",
        "nav",
        "aum",
        "fund",
        "hdfc",
        "motilal",
        "midcap",
        "large cap",
        "largecap",
        "flexi cap",
        "flexicap",
        "index fund",
        "etf",
        "mid cap",
        "small cap",
        "smallcap",
        "nifty",
        "sensex",
        "equity",
        "debt fund",
        "returns",
        "cagr",
        "portfolio",
        "diversify",
        "invest",
        "redemption",
    ]
)

# Explanatory / comparative intent keywords: hybrid_query requires at least one
# of these alongside a metric keyword.  General "tell me about X fund" queries
# must NOT match here so they fall through to mf_query (standard/Groq).
_HYBRID_EXPLANATORY_KEYWORDS = frozenset(
    [
        "explain",
        "compare",
        "comparison",
        "why",
        "difference",
        "better",
        "better than",
        "should i",
        "tell me more",
        "understand",
        "how does",
        "how do",
        "what makes",
        "vs",
        "versus",
        "pros and cons",
        "worth it",
        "matters",
    ]
)

# Direct metric keywords: specific data-point questions that should prefer
# structured lookup over free-text RAG when a fund is also identifiable.
_DIRECT_METRIC_KEYWORDS = frozenset(
    [
        "expense ratio",
        "exit load",
        "nav",
        "net asset value",
        "aum",
        "fund size",
        "corpus",
        "minimum sip",
        "min sip",
        "minimum investment",
        "minimum lump",
        "top holdings",
        "holdings",
        "sector allocation",
        "asset allocation",
        "returns of",
        "1 year return",
        "3 year return",
        "5 year return",
        "cagr of",
        "risk level",
        "riskometer",
        "benchmark",
        "rating",
        "ter",
    ]
)


def _classify_intent_inner(message: str) -> IntentLabel:
    """Core keyword-based classification logic (no side effects)."""
    text = message.strip()
    lower = text.lower()

    # Disallowed requests short-circuit immediately (Rules R13).
    if _DISALLOWED_PATTERNS.search(lower):
        return "disallowed"

    has_booking = any(kw in lower for kw in _BOOKING_KEYWORDS)
    has_fee = any(kw in lower for kw in _FEE_KEYWORDS)
    has_mf = any(kw in lower for kw in _MF_KEYWORDS)
    has_direct_metric = any(kw in lower for kw in _DIRECT_METRIC_KEYWORDS)
    has_explanatory = any(kw in lower for kw in _HYBRID_EXPLANATORY_KEYWORDS)
    has_metric = has_direct_metric or has_fee

    # direct_metric_query: specific metric + fund context present, no explanatory intent.
    # Pure metric lookups ("What is the NAV of HDFC Flexi Cap?") go here — zero LLM call.
    # When explanatory intent is also present, fall through to hybrid_query instead.
    if has_direct_metric and has_mf and not has_explanatory and not has_booking:
        return "direct_metric_query"

    if has_booking and not has_fee and not has_mf:
        return "booking_intent"

    # hybrid_query: ONLY when a metric keyword AND explanatory/comparative intent
    # are both present.  "Tell me about HDFC Flexi Cap Fund" must NOT match here
    # (no metric keyword → has_metric=False → routes to mf_query via Groq instead).
    if has_metric and has_explanatory:
        return "hybrid_query"

    if has_fee:
        return "fee_query"

    if has_mf:
        return "mf_query"

    # Booking combined with a question → hybrid route through MF.
    if has_booking and (has_mf or has_fee):
        return "hybrid_query"

    return "out_of_scope"


def classify_intent(message: str) -> IntentLabel:
    """Fast keyword-based intent classification with audit logging.

    Returns a stable IntentLabel string (Rules D3: centralized enum).
    """
    intent = _classify_intent_inner(message)
    tier = assign_model_tier(intent)
    model_tier = "heavy" if tier == "heavy" else "standard"
    provider = "gemini" if tier == "heavy" else ("none" if tier == "light" else "groq")
    logger.info(
        "intent_classified",
        extra={
            "intent": intent,
            "tier": tier,
            "model_tier": model_tier,
            "provider": provider,
        },
    )
    return intent


def assign_model_tier(intent: IntentLabel) -> Literal["light", "standard", "heavy"]:
    LIGHT = {"out_of_scope", "disallowed", "direct_metric_query"}
    STANDARD = {"mf_query", "fee_query", "booking_intent"}
    HEAVY = {"hybrid_query"}
    if intent in LIGHT:
        return "light"
    if intent in HEAVY:
        return "heavy"
    return "standard"


DISALLOWED_RESPONSES: dict[str, str] = {
    "disallowed": (
        "I'm not able to give personalised investment advice, predictions, or recommendations. "
        "I can explain mutual fund concepts and fees from Groww's product pages. "
        "What would you like to understand about a specific fund or fee? "
        "This is general information only, not personalised financial advice."
    ),
    "out_of_scope": (
        "I can help with mutual fund information and fee explanations from Groww's product pages. "
        "Try asking about a specific fund's expense ratio, exit load, or how a particular fund category works. "
        "This is general information only, not personalised financial advice."
    ),
}
