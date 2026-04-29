"""Intent classification for customer chat messages (Phase 4, Rules R13).

Classifies incoming messages into one of the IntentLabels so the
customer_router_service can route correctly:

- mf_query       → RAG retrieval on mutual fund pages
- fee_query      → RAG retrieval on expense ratio / exit load content
- hybrid_query   → Both MF + fee content needed in one response (Rules P4.4)
- booking_intent → Hand off to booking response (Phase 5+ wiring)
- out_of_scope   → Safe educational fallback
- disallowed     → Refuse early (Rules R13): financial advice, PII, harmful requests

Classification is keyword-first (fast, deterministic) to keep latency low (Rules L7).
"""

from __future__ import annotations

import re

from app.schemas.rag import IntentLabel

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


def classify_intent(message: str) -> IntentLabel:
    """Fast keyword-based intent classification.

    Returns a stable IntentLabel string (Rules D3: centralized enum).
    """
    text = message.strip()
    lower = text.lower()

    # Disallowed requests short-circuit immediately (Rules R13).
    if _DISALLOWED_PATTERNS.search(lower):
        return "disallowed"

    has_booking = any(kw in lower for kw in _BOOKING_KEYWORDS)
    has_fee = any(kw in lower for kw in _FEE_KEYWORDS)
    has_mf = any(kw in lower for kw in _MF_KEYWORDS)

    if has_booking and not has_fee and not has_mf:
        return "booking_intent"

    if has_mf and has_fee:
        return "hybrid_query"

    if has_fee:
        return "fee_query"

    if has_mf:
        return "mf_query"

    # Booking combined with a question → hybrid route through MF.
    if has_booking and (has_mf or has_fee):
        return "hybrid_query"

    return "out_of_scope"


DISALLOWED_RESPONSES: dict[str, str] = {
    "disallowed": (
        "I'm not able to give personalised investment advice, predictions, or recommendations. "
        "I can explain mutual fund concepts and fees from Groww's product pages. "
        "What would you like to understand about a specific fund or fee?"
    ),
    "out_of_scope": (
        "I can help with mutual fund information and fee explanations from Groww's product pages. "
        "Try asking about a specific fund's expense ratio, exit load, or how a particular fund category works."
    ),
}
