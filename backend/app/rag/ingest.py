"""Shared ingestion utilities for Phase 2 (reviews) and Phase 4 (MF/fee web documents).

Phase 2: cleaning + normalization of Play Store review text before any LLM usage.
Phase 4: HTML cleaning and extraction for MF/fee corpus pages (Rules G19, P4.8).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.schemas.pulse import NormalizedReview, RawReview


_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE_RE = re.compile(r"\b(?:\+?91[\s-]?)?[6-9]\d{9}\b")


def clean_text(text: str) -> str:
    t = text or ""
    t = re.sub(r"<[^>]+>", " ", t)  # strip HTML-ish markup
    t = re.sub(r"\s+", " ", t).strip()
    return t


def minimize_pii(text: str) -> str:
    t = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    t = _PHONE_RE.sub("[REDACTED_PHONE]", t)
    return t


def is_englishish(text: str) -> bool:
    if not text:
        return False
    letters = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    return (letters / max(len(text), 1)) >= 0.45


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class NormalizeStats:
    input_rows: int
    kept: int
    dropped_short: int
    dropped_non_english: int
    dropped_dupe: int


def normalize_raw_reviews(raw: list[RawReview], min_len: int = 20) -> tuple[list[NormalizedReview], NormalizeStats]:
    out: list[NormalizedReview] = []
    seen_hashes: set[str] = set()
    seen_ids: set[str] = set()

    dropped_short = 0
    dropped_non_english = 0
    dropped_dupe = 0

    for r in raw:
        t = minimize_pii(clean_text(r.text))
        if len(t) < min_len:
            dropped_short += 1
            continue
        if not is_englishish(t):
            dropped_non_english += 1
            continue
        h = content_hash(t)
        if r.review_id in seen_ids or h in seen_hashes:
            dropped_dupe += 1
            continue
        seen_ids.add(r.review_id)
        seen_hashes.add(h)
        out.append(
            NormalizedReview(
                review_id=r.review_id,
                rating=r.rating,
                text=t,
                review_date=r.review_date,
                found_review_helpful=r.found_review_helpful,
                device=r.device,
                content_hash=h,
            )
        )

    return out, NormalizeStats(
        input_rows=len(raw),
        kept=len(out),
        dropped_short=dropped_short,
        dropped_non_english=dropped_non_english,
        dropped_dupe=dropped_dupe,
    )


# ---------------------------------------------------------------------------
# Phase 4: MF / fee web document ingestion (Rules P4.8, G19)
# ---------------------------------------------------------------------------

# Boilerplate patterns common on Groww fund pages.
_BOILERPLATE_RE = re.compile(
    r"(cookie|privacy policy|terms of use|javascript|loading\.\.\.|back to top"
    r"|share on|follow us|download app|install groww|groww app)",
    re.I,
)


def clean_html_content(html: str) -> str:
    """Strip HTML tags and known boilerplate from raw page HTML.

    Requires beautifulsoup4; falls back to regex strip if not installed (Rules G7).
    """
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html, "lxml")
        # Remove script, style, nav, footer, header blocks.
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
    except ImportError:
        text = re.sub(r"<[^>]+>", "\n", html)

    # Normalise whitespace.
    lines = [ln.strip() for ln in text.splitlines()]
    # Drop boilerplate lines and very short fragments.
    kept = [ln for ln in lines if ln and len(ln) > 12 and not _BOILERPLATE_RE.search(ln)]
    return "\n".join(kept)


def normalize_document_content(raw_text: str) -> str:
    """Normalize cleaned web document text: collapse whitespace, remove duplicate lines."""
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    seen: set[str] = set()
    deduped: list[str] = []
    for ln in lines:
        key = ln.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(ln)
    return "\n".join(deduped)

