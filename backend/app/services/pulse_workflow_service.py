"""Weekly Pulse workflow (Phase 2).

Implements the mandatory pipeline:
raw persist -> cleaning -> normalization -> theme generation -> pulse generation -> persist pulse.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from uuid import uuid4

from app.core.config import Settings
from app.core.context import correlation_id as _cid_var
from fastapi import HTTPException
from app.llm.gemini_client import GeminiClient
from app.llm.groq_client import GroqClient
from app.llm.prompt_registry import pulse_theme_prompt, weekly_pulse_prompt
from app.repositories.pulse_repository import PulseRepository, get_pulse_repository
from app.rag.ingest import normalize_raw_reviews
from app.services.review_sampler import sample_reviews_for_theme_prompt
from app.schemas.pulse import (
    NormalizedReview,
    PulseGenerateRequest,
    PulseMetrics,
    PulseQuote,
    PulseTheme,
    RawReview,
    WeeklyPulse,
)

logger = logging.getLogger(__name__)


def _fixture_raw_reviews() -> list[RawReview]:
    today = date.today()
    rows: list[RawReview] = [
        RawReview(review_id="r1", rating=1, text="App keeps crashing during SIP setup. Please fix.", review_date=today),
        RawReview(review_id="r2", rating=2, text="KYC verification takes too long and fails often.", review_date=today),
        RawReview(review_id="r3", rating=4, text="Great UI but withdrawals are confusing. Need clearer steps.", review_date=today),
        RawReview(review_id="r4", rating=1, text="Login OTP not received on time. Very frustrating.", review_date=today),
        RawReview(review_id="r5", rating=5, text="Overall smooth experience. Love the portfolio view.", review_date=today),
        RawReview(review_id="r6", rating=3, text="Support chat is slow. Response takes hours.", review_date=today),
    ]
    return rows


def _rule_based_themes(normalized: list[NormalizedReview]) -> tuple[list[PulseTheme], list[PulseQuote]]:
    texts = [n.text.lower() for n in normalized]
    keywords = {
        "crash": ["crash", "crashing"],
        "otp/login": ["otp", "login", "sign in"],
        "kyc": ["kyc", "verification"],
        "withdrawal": ["withdraw", "withdrawal", "redeem"],
        "support": ["support", "chat", "help"],
    }
    theme_counts: dict[str, int] = {}
    for theme, kws in keywords.items():
        theme_counts[theme] = sum(any(k in t for k in kws) for t in texts)

    themes: list[PulseTheme] = []
    for theme, cnt in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True):
        if cnt <= 0:
            continue
        themes.append(PulseTheme(theme=theme, summary=f"Mentions related to {theme}.", count=cnt))
    if not themes:
        themes = [PulseTheme(theme="general", summary="Mixed feedback without a dominant theme.", count=len(normalized))]

    quotes: list[PulseQuote] = []
    for n in normalized[: min(5, len(normalized))]:
        quotes.append(PulseQuote(review_id=n.review_id, quote=n.text[:180], rating=n.rating))
    return themes[:6], quotes


async def generate_weekly_pulse(settings: Settings, req: PulseGenerateRequest) -> WeeklyPulse:
    repo: PulseRepository = get_pulse_repository(settings)

    raw_rows: list[RawReview] = []
    cleaned: list[NormalizedReview] = []

    if req.use_fixture:
        raw_rows = _fixture_raw_reviews()
        await repo.persist_raw_reviews(raw_rows)
        logger.info(
            "pipeline_stage raw_persisted",
            extra={"stage": "raw_persisted", "count": len(raw_rows), "correlation_id": _cid_var.get()},
        )
        cleaned, _ = normalize_raw_reviews(raw_rows)
        await repo.persist_normalized_reviews(cleaned)
        logger.info(
            "pipeline_stage normalized_persisted",
            extra={"stage": "normalized_persisted", "count": len(cleaned), "correlation_id": _cid_var.get()},
        )
    else:
        # Use real ingested/normalized data (created by scripts/ingest_sources.py).
        cleaned = await repo.get_recent_normalized_reviews(lookback_weeks=req.lookback_weeks, limit=800)
        if not cleaned:
            raise HTTPException(status_code=424, detail="no_normalized_reviews_available")
        logger.info(
            "pipeline_stage normalized_persisted",
            extra={"stage": "normalized_persisted", "count": len(cleaned), "correlation_id": _cid_var.get()},
        )

    degraded = False
    degraded_reason: str | None = None

    # Theme generation (Groq) over normalized text only
    themes: list[PulseTheme]
    quotes: list[PulseQuote]
    # `segmented_text` is bounded for Groq TPM only.
    # `cleaned` still holds ALL reviews and is used for metrics and quotes.
    segmented_text: list[str] = sample_reviews_for_theme_prompt(
        reviews=cleaned,
        max_segments=settings.pulse_max_theme_segments,
        max_chars_per_segment=800,
    )

    _approx_tokens = int(sum(len(s) for s in segmented_text) * 1.3 / 4)
    logger.info(
        "theme_prompt_budget",
        extra={
            "reviews_total": len(cleaned),               # all 200
            "segments_to_groq": len(segmented_text),     # bounded sample
            "approx_tokens": _approx_tokens,
        },
    )
    if _approx_tokens > 5000:
        logger.warning(
            "theme_prompt_near_tpm_limit",
            extra={
                "approx_tokens": _approx_tokens,
                "hint": "lower PULSE_MAX_THEME_SEGMENTS in .env",
            },
        )

    if segmented_text and settings.groq_api_key:
        try:
            groq = GroqClient(settings)
            prompt = pulse_theme_prompt(segmented_text)
            out = groq.chat_json(prompt=prompt)
            payload = json.loads(out) if out else {}
            themes = [PulseTheme.model_validate(t) for t in (payload.get("themes") or [])][:6]
            quotes = [PulseQuote.model_validate(q) for q in (payload.get("quotes") or [])][:8]
            # If Groq returns fewer than 3 quotes, supplement from full cleaned list
            if len(quotes) < 3:
                seen_ids = {q.review_id for q in quotes}
                fallback_quotes = sorted(
                    cleaned,
                    key=lambda r: abs(r.rating - 3),  # most extreme ratings first
                    reverse=True,
                )
                for r in fallback_quotes:
                    if r.review_id not in seen_ids and len(quotes) < 8:
                        quotes.append(
                            PulseQuote(
                                review_id=r.review_id,
                                quote=r.text[:180],
                                rating=r.rating,
                            )
                        )
                        seen_ids.add(r.review_id)
            if not themes:
                raise ValueError("empty_themes")
        except Exception as exc:
            if settings.app_env not in ("prod", "staging"):
                raise
            degraded = True
            exc_str = str(exc).lower()
            if any(k in exc_str for k in ("rate_limit", "tokens_per_minute", "tpm")):
                logger.warning(
                    "groq_tpm_limit_hit",
                    extra={
                        "segments_sent": len(segmented_text),
                        "approx_tokens": _approx_tokens,
                        "hint": "lower PULSE_MAX_THEME_SEGMENTS; current value too high for free tier",
                    },
                )
                degraded_reason = "groq_tpm_limit"
            else:
                degraded_reason = f"groq_degraded:{type(exc).__name__}"
            themes, quotes = _rule_based_themes(cleaned)
    else:
        degraded = True
        degraded_reason = "groq_key_missing_or_no_reviews"
        themes, quotes = _rule_based_themes(cleaned)
    logger.info(
        "pipeline_stage themes_generated",
        extra={"stage": "themes_generated", "count": len(themes), "correlation_id": _cid_var.get()},
    )

    # Pulse synthesis (Gemini) with schema validation; fallback deterministic compose
    narrative = ""
    actions: list[str] = []
    if segmented_text and settings.gemini_api_key:
        try:
            gemini = GeminiClient(settings)
            theme_json = json.dumps(
                {"themes": [t.model_dump() for t in themes], "quotes": [q.model_dump() for q in quotes]},
                ensure_ascii=False,
            )
            out = await gemini.generate_text(weekly_pulse_prompt(theme_json))
            payload = json.loads(out) if out and out.strip().startswith("{") else {}
            narrative = str(payload.get("narrative") or "").strip()
            actions = [str(a) for a in (payload.get("recommended_actions") or [])][:6]
            if not narrative:
                raise ValueError("empty_narrative")
        except Exception as exc:
            if settings.app_env not in ("prod", "staging"):
                raise
            degraded = True
            degraded_reason = (degraded_reason + ";") if degraded_reason else ""
            degraded_reason += f"gemini_degraded:{type(exc).__name__}"
    else:
        degraded = True
        degraded_reason = (degraded_reason + ";") if degraded_reason else ""
        degraded_reason += "gemini_key_missing_or_no_reviews"

    if not narrative:
        narrative = "This week’s reviews highlight a few recurring friction points and a smaller set of positive signals."
    if not actions:
        actions = [
            "Triage top recurring failure points and assign owners.",
            "Add targeted instrumentation for the highest-frequency theme.",
            "Draft a customer-facing status update for known issues where applicable.",
        ]

    # Uses all cleaned reviews (full 200), not the sampled prompt segments
    avg = round(sum(r.rating for r in cleaned) / max(len(cleaned), 1), 2) if cleaned else 0.0
    metrics = PulseMetrics(reviews_considered=len(cleaned), average_rating=avg, lookback_weeks=req.lookback_weeks)

    pulse = WeeklyPulse(
        pulse_id=f"PULSE-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid4().hex[:8]}",
        metrics=metrics,
        themes=themes,
        quotes=quotes,
        recommended_actions=actions,
        narrative=narrative,
        degraded=degraded,
        degraded_reason=degraded_reason,
    )

    await repo.create_weekly_pulse(pulse)
    logger.info(
        "pipeline_stage pulse_persisted",
        extra={"stage": "pulse_persisted", "pulse_id": pulse.pulse_id, "correlation_id": _cid_var.get()},
    )
    logger.info(
        "pulse_generated",
        extra={
            "correlation_id": _cid_var.get(),
            "degraded": degraded,
            "reviews_considered": metrics.reviews_considered,
        },
    )
    return pulse


async def get_current_pulse(settings: Settings) -> WeeklyPulse | None:
    return await get_pulse_repository(settings).get_current_pulse()


async def get_pulse_history(settings: Settings, limit: int = 20) -> list[WeeklyPulse]:
    return await get_pulse_repository(settings).get_pulse_history(limit=limit)
