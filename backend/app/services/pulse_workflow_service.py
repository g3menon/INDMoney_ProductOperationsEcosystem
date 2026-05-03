"""Weekly Pulse workflow (Phase 2).

Implements the mandatory pipeline:
raw persist -> cleaning -> normalization -> theme generation -> pulse generation -> persist pulse.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
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


_FIXTURE_TOPICS: list[tuple[str, int, str]] = [
    ("kyc", 2, "KYC verification keeps failing even after uploading documents. I need clearer next steps."),
    ("sip", 1, "SIP mandate setup failed twice and the app did not explain what happened."),
    ("withdrawal", 2, "Withdrawal timelines are confusing. I cannot tell when money will reach my bank."),
    ("tax", 3, "Capital gains statements and tax documents are hard to find during filing season."),
    ("login", 1, "OTP arrives late during login and the session expires before I can continue."),
    ("performance", 2, "The portfolio screen loads slowly when checking mutual fund details."),
    ("support", 2, "Support chat takes too long when I need help with account changes."),
    ("nominee", 3, "Nominee update steps are unclear and I want advisor help before changing details."),
    ("positive", 5, "The UI is clean and portfolio tracking is useful once everything is set up."),
]


def _fixture_raw_reviews(target: int = 180) -> list[RawReview]:
    today = date.today()
    batch = uuid4().hex[:6]
    rows: list[RawReview] = []
    for idx in range(target):
        topic, rating, text = _FIXTURE_TOPICS[idx % len(_FIXTURE_TOPICS)]
        rows.append(
            RawReview(
                review_id=f"fixture-{today:%Y%m%d}-{batch}-{idx + 1:03d}",
                rating=rating,
                text=f"{text} Case {idx + 1} from {topic} feedback.",
                review_date=today,
            )
        )
    return rows


def _rule_based_themes(normalized: list[NormalizedReview]) -> tuple[list[PulseTheme], list[PulseQuote]]:
    texts = [n.text.lower() for n in normalized]
    keywords = {
        "KYC and onboarding friction": ["kyc", "verification", "document", "onboarding"],
        "SIP and mandate reliability": ["sip", "mandate", "autopay"],
        "Withdrawals and timelines": ["withdraw", "withdrawal", "redeem", "timeline"],
        "Statements and tax documents": ["statement", "tax", "capital gains", "filing"],
        "Login and trust interruptions": ["otp", "login", "sign in", "session"],
        "Support and account changes": ["support", "chat", "nominee", "account changes"],
    }
    theme_counts: dict[str, int] = {}
    for theme, kws in keywords.items():
        theme_counts[theme] = sum(any(k in t for k in kws) for t in texts)

    themes: list[PulseTheme] = []
    for theme, cnt in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True):
        if cnt <= 0:
            continue
        themes.append(
            PulseTheme(
                theme=theme,
                summary=(
                    f"{cnt} customers mention {theme.lower()}, indicating repeated operational friction "
                    "that can drive advisor demand or support escalation."
                ),
                count=cnt,
            )
        )
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
            out = groq.chat_json(prompt=prompt, model=settings.llm_standard_model)
            payload = _parse_json_object(out)
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
                logger.warning(
                    "groq_theme_generation_degraded",
                    extra={"error_type": type(exc).__name__, "error": str(exc)[:160]},
                )
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
            payload = _parse_json_object(out)
            narrative = str(payload.get("narrative") or "").strip()
            actions = [str(a) for a in (payload.get("recommended_actions") or [])][:6]
            if not narrative:
                raise ValueError("empty_narrative")
        except Exception as exc:
            degraded = True
            logger.warning(
                "gemini_pulse_generation_degraded",
                extra={"error_type": type(exc).__name__, "error": str(exc)[:160]},
            )
            degraded_reason = (degraded_reason + ";") if degraded_reason else ""
            degraded_reason += f"gemini_degraded:{type(exc).__name__}"
    else:
        degraded = True
        degraded_reason = (degraded_reason + ";") if degraded_reason else ""
        degraded_reason += "gemini_key_missing_or_no_reviews"

    if not narrative:
        top_theme = themes[0].theme if themes else "customer operations"
        narrative = (
            f"This week's feedback is concentrated around {top_theme}. "
            f"The pulse considered {len(cleaned)} normalized reviews and shows where repeated customer friction may "
            "increase support volume, advisor booking intent, or trust risk. Use the themes and quotes below to decide "
            "which workflows need product fixes, clearer communication, or advisor enablement."
        )
    if not actions:
        actions = [
            "Triage top recurring failure points and assign owners.",
            "Add targeted instrumentation for the highest-frequency theme.",
            "Draft a customer-facing status update for known issues where applicable.",
        ]

    # Uses all cleaned reviews (full 200), not the sampled prompt segments
    avg = round(sum(r.rating for r in cleaned) / max(len(cleaned), 1), 2) if cleaned else 0.0
    metrics = PulseMetrics(reviews_considered=len(cleaned), average_rating=avg, lookback_weeks=req.lookback_weeks)
    if len(cleaned) < 150:
        degraded = True
        degraded_reason = (degraded_reason + ";") if degraded_reason else ""
        degraded_reason += f"low_review_volume:{len(cleaned)}"

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


def _parse_json_object(raw: str | None) -> dict:
    if not raw:
        return {}
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)
