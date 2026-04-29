"""
Stratified review sampler for Groq theme prompt.

IMPORTANT: This sampler is a PROMPT-SHAPING step only.
It reduces the number of segments sent to Groq to stay within TPM limits.
It does NOT affect how many reviews are collected, stored, or counted.
All 200 reviews are still used for metrics, quotes, and normalization.
"""

from __future__ import annotations

import logging
import math
import random

from app.rag.chunk import segment_review_text
from app.schemas.pulse import NormalizedReview

logger = logging.getLogger(__name__)


def sample_reviews_for_theme_prompt(
    reviews: list[NormalizedReview],
    max_segments: int = 60,
    max_chars_per_segment: int = 800,
) -> list[str]:
    """
    Selects a representative stratified sample from all reviews
    and returns bounded segments for Groq theme generation.

    All 200 reviews remain available in the caller for metrics and quotes.
    Only the returned segments list is bounded.
    """
    if not reviews:
        return []

    # Group by rating bucket
    buckets: dict[str, list[NormalizedReview]] = {
        "negative": [r for r in reviews if r.rating in (1, 2)],
        "neutral": [r for r in reviews if r.rating == 3],
        "positive": [r for r in reviews if r.rating in (4, 5)],
    }

    total = len(reviews)

    # Proportional allocation — minimum 10 per bucket if available
    allocated: dict[str, int] = {}
    for bucket, items in buckets.items():
        proportion = len(items) / total if total > 0 else 0
        allocated[bucket] = max(
            min(10, len(items)),
            math.floor(proportion * max_segments),
        )

    # Scale down if over budget
    total_allocated = sum(allocated.values())
    if total_allocated > max_segments:
        scale = max_segments / total_allocated
        allocated = {k: max(1, int(v * scale)) for k, v in allocated.items()}

    # Select reviews with most signal (longest text) per bucket
    selected: list[NormalizedReview] = []
    for bucket, items in buckets.items():
        sorted_items = sorted(items, key=lambda r: len(r.text), reverse=True)
        selected.extend(sorted_items[: allocated[bucket]])

    # Segment selected reviews
    segments: list[str] = []
    for r in selected:
        segments.extend(segment_review_text(r.text, max_chars=max_chars_per_segment))

    # Hard cap
    segments = segments[:max_segments]

    # Shuffle with fixed seed — reproducible across runs
    random.Random(42).shuffle(segments)

    approx_tokens = int(sum(len(s) for s in segments) * 1.3 / 4)

    logger.info(
        "review_sampler_complete",
        extra={
            "total_reviews_available": total,       # all 200 available
            "sampled_for_groq": len(selected),      # subset used for Groq prompt
            "segments_to_groq": len(segments),      # actual segments sent
            "approx_tokens": approx_tokens,
            "bucket_allocation": allocated,
        },
    )

    return segments
