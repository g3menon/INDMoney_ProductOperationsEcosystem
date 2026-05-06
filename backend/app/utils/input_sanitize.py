"""
Pre-flight input sanitization for user chat queries.
Runs BEFORE the query is sent to the LLM. Blocking mode -
if a forbidden pattern is found, return a safe refusal message
instead of passing the query forward.
"""

from __future__ import annotations

import re

_LAST_UPDATED_SUFFIX = "Last updated from sources: today"

PII_BLOCKED_MESSAGE = (
    "I cannot process messages containing personal information like Aadhaar, PAN, "
    "account numbers, emails, or phone numbers. Please write your question without "
    f"sharing any personal details. {_LAST_UPDATED_SUFFIX}"
)

INVESTMENT_ADVICE_MESSAGE = (
    "I cannot provide personalized investment recommendations. For fund comparisons "
    "and details, visit Groww's help centre: https://support.groww.in "
    f"{_LAST_UPDATED_SUFFIX}"
)

PERFORMANCE_CLAIM_MESSAGE = (
    "Performance figures are historical and may not be repeated. For the most "
    "up-to-date factsheet, visit the fund page on groww.in or check the scheme "
    "information document on AMFI's website: "
    f"https://www.amfiindia.com/nav-history-download {_LAST_UPDATED_SUFFIX}"
)

THIRD_PARTY_SOURCE_MESSAGE = (
    "I can only provide information from official Groww sources (groww.in pages and "
    "the official app listing). I do not reference third-party blogs, screenshots, "
    f"or external websites. {_LAST_UPDATED_SUFFIX}"
)

_PII_PATTERNS = (
    re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
    re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.I),
    re.compile(r"\b\d{9,18}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"(?:\+91[\s-]?)?\b[6-9]\d{9}\b"),
)

_INVESTMENT_ADVICE_PATTERNS = (
    re.compile(r"\bwhich\s+fund\s+should\s+i\s+(?:invest\s+in|buy|choose)\b", re.I),
    re.compile(r"\brecommend\s+(?:me\s+)?(?:a\s+)?fund\b", re.I),
    re.compile(r"\bbest\s+fund\s+to\s+invest\b", re.I),
    re.compile(r"\bwill\s+.+\s+give\s+good\s+returns\b", re.I),
    re.compile(r"\bshould\s+i\s+(?:buy|sell)\b", re.I),
    re.compile(r"\bpredict\s+(?:the\s+)?nav\b", re.I),
    re.compile(r"\bguaranteed?\s+returns?\b", re.I),
    re.compile(r"\bhow\s+much\s+will\s+i\s+earn\b", re.I),
)

_PERFORMANCE_CLAIM_PATTERNS = (
    re.compile(r"\breturns?\b", re.I),
    re.compile(r"\breturn\s+on\s+investment\b", re.I),
    re.compile(r"\broi\b", re.I),
    re.compile(r"\bperformance\b", re.I),
    re.compile(r"\bhow\s+much\s+did\s+it\s+grow\b", re.I),
    re.compile(r"\bwill\s+go\s+(?:up|down)\b", re.I),
    re.compile(r"\bis\s+going\s+up\b", re.I),
    re.compile(r"\b\d+\s+year\s+cagr\b", re.I),
    re.compile(r"\bcagr\b", re.I),
    re.compile(r"\bcompounded\b", re.I),
    re.compile(r"\bannuali[sz]ed\s+return\b", re.I),
)

_THIRD_PARTY_SOURCE_PATTERNS = (
    re.compile(r"\bmoneycontrol\s+says\b", re.I),
    re.compile(r"\bmlpandai\b", re.I),
    re.compile(r"\bscreener\.in\b", re.I),
    re.compile(r"\breddit\b", re.I),
    re.compile(r"\byoutube\b", re.I),
    re.compile(r"\bthird[-\s]?party\s+blog\b", re.I),
    re.compile(r"\bblog\s+post\b", re.I),
    re.compile(r"\bscreenshot\b", re.I),
    re.compile(r"\bbackend\s+data\b", re.I),
    re.compile(r"\badmin\s+panel\b", re.I),
)


def sanitize_user_query(query: str) -> tuple[str | None, str | None]:
    """Return (sanitized_query, error_message) for a customer chat query."""
    normalized = (query or "").strip()

    if any(pattern.search(normalized) for pattern in _PII_PATTERNS):
        return None, PII_BLOCKED_MESSAGE

    if any(pattern.search(normalized) for pattern in _INVESTMENT_ADVICE_PATTERNS):
        return None, INVESTMENT_ADVICE_MESSAGE

    if any(pattern.search(normalized) for pattern in _PERFORMANCE_CLAIM_PATTERNS):
        return None, PERFORMANCE_CLAIM_MESSAGE

    if any(pattern.search(normalized) for pattern in _THIRD_PARTY_SOURCE_PATTERNS):
        return None, THIRD_PARTY_SOURCE_MESSAGE

    return normalized, None
