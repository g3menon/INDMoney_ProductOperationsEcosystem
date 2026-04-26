"""Shared ingestion utilities for Phase 2.

Implements cleaning + normalization rules for Play Store review text before any LLM usage.
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

