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
        "10 year return",
        "ten year return",
        "return calculator",
        "investment return",
        "returns and rankings",
        "ranking",
        "rank",
        "advanced ratios",
        "sharpe",
        "sortino",
        "alpha",
        "beta",
        "standard deviation",
        "fund management",
        "fund manager",
        "cagr of",
        "risk level",
        "riskometer",
        "benchmark",
        "rating",
        "ter",
    ]
)

_REVIEW_KEYWORDS = frozenset(
    [
        "review",
        "reviews",
        "playstore",
        "play store",
        "user feedback",
        "complaint",
        "complaints",
        "rating",
        "ratings",
        "1 star",
        "2 star",
        "3 star",
        "negative review",
        "positive review",
        "users say",
        "users are saying",
        "users mention",
        "feedback",
        "what users",
        "user complaint",
        "user experience",
        "app review",
    ]
)

_TREND_KEYWORDS = frozenset(
    [
        "trend",
        "trends",
        "trending",
        "more than last",
        "less than last",
        "last month",
        "last week",
        "last quarter",
        "compared to",
        "over time",
        "increase",
        "increased",
        "decrease",
        "decreased",
        "rising",
        "falling",
        "growing",
        "volume",
        "spike",
        "surge",
        "drop in",
        "month on month",
        "week on week",
        "historical",
    ]
)

_ISSUE_DIAGNOSIS_KEYWORDS = frozenset(
    [
        "why",
        "root cause",
        "reason",
        "diagnosis",
        "regression",
        "bug",
        "broken",
        "crash",
        "crashes",
        "not working",
        "issue",
        "issues",
        "problem",
        "problems",
        "what changed",
        "changed in version",
        "version",
        "v5",
        "v4",
        "hotfix",
        "after update",
        "after upgrade",
        "since update",
        "degraded",
        "degradation",
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
    has_review = any(kw in lower for kw in _REVIEW_KEYWORDS)
    has_trend = any(kw in lower for kw in _TREND_KEYWORDS)
    has_issue = any(kw in lower for kw in _ISSUE_DIAGNOSIS_KEYWORDS)

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
    if (has_metric or has_mf) and has_explanatory:
        return "hybrid_query"

    # issue_diagnosis first — "why" is specific, must beat trend and review
    if has_issue and not has_direct_metric and not has_booking:
        return "issue_diagnosis_query"

    # trend before review — trend is a modifier of review queries
    if has_trend and not has_direct_metric and not has_booking:
        return "trend_query"

    # product review
    if has_review and not has_direct_metric and not has_booking:
        return "product_review_query"

    if has_fee:
        return "fee_query"

    if has_mf:
        return "mutual_fund_info_query"

    # Booking combined with a question → hybrid route through MF.
    if has_booking and (has_mf or has_fee):
        return "hybrid_query"

    return "out_of_scope"


def classify_intent(message: str) -> IntentLabel:
    """Fast keyword-based intent classification with audit logging.

    Returns a stable IntentLabel string (Rules D3: centralized enum).
    """
    intent = _classify_intent_inner(message)
    lower = message.lower()
    matched_kw = _matched_keyword(intent, lower)
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
            "query_len": len(message),
            "matched_keyword": matched_kw,
        },
    )
    return intent


def _first_match(lower: str, keywords: frozenset[str]) -> str:
    return next((kw for kw in keywords if kw in lower), "default")


def _matched_keyword(intent: IntentLabel, lower: str) -> str:
    if intent == "disallowed":
        match = _DISALLOWED_PATTERNS.search(lower)
        return match.group(1) if match else "default"
    keyword_sets = {
        "booking_intent": _BOOKING_KEYWORDS,
        "direct_metric_query": _DIRECT_METRIC_KEYWORDS,
        "hybrid_query": _HYBRID_EXPLANATORY_KEYWORDS,
        "issue_diagnosis_query": _ISSUE_DIAGNOSIS_KEYWORDS,
        "trend_query": _TREND_KEYWORDS,
        "product_review_query": _REVIEW_KEYWORDS,
        "fee_query": _FEE_KEYWORDS,
        "mutual_fund_info_query": _MF_KEYWORDS,
    }
    return _first_match(lower, keyword_sets.get(intent, frozenset()))


def assign_model_tier(intent: IntentLabel) -> Literal["light", "standard", "heavy"]:
    LIGHT = {"out_of_scope", "disallowed", "direct_metric_query"}
    STANDARD = {
        "mutual_fund_info_query",
        "fee_query",
        "booking_intent",
        "product_review_query",
        "trend_query",
    }
    HEAVY = {"hybrid_query", "issue_diagnosis_query"}
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
        "I can help with Groww product-operations topics: user reviews, "
        "Play Store feedback, performance trends, booking an advisor, "
        "or mutual fund fee and scheme information. "
        "What would you like to look into? "
        "This is general information only, not personalised financial advice."
    ),
}
