"""Weekly Pulse workflow (Phase 2).

Implements the mandatory pipeline:
raw persist -> cleaning -> normalization -> theme generation -> pulse generation -> persist pulse.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.llm.gemini_client import GeminiClient
from app.llm.groq_client import GroqClient
from app.llm.prompt_registry import pulse_theme_prompt, weekly_pulse_prompt
from app.repositories.pulse_repository import PulseRepository, get_pulse_repository
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


_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE_RE = re.compile(r"\b(?:\+?91[\s-]?)?[6-9]\d{9}\b")


def _clean_text(text: str) -> str:
    t = text or ""
    t = re.sub(r"<[^>]+>", " ", t)  # strip markup
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _minimize_pii(text: str) -> str:
    t = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    t = _PHONE_RE.sub("[REDACTED_PHONE]", t)
    return t


def _is_englishish(text: str) -> bool:
    if not text:
        return False
    letters = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    return (letters / max(len(text), 1)) >= 0.45


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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

    raw_rows = _fixture_raw_reviews() if req.use_fixture else []
    await repo.persist_raw_reviews(raw_rows)

    cleaned: list[NormalizedReview] = []
    seen_hashes: set[str] = set()
    for r in raw_rows:
        t = _minimize_pii(_clean_text(r.text))
        if len(t) < 20:
            continue
        if not _is_englishish(t):
            continue
        h = _content_hash(t)
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        cleaned.append(
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

    await repo.persist_normalized_reviews(cleaned)

    degraded = False
    degraded_reason: str | None = None

    # Theme generation (Groq) over normalized text only
    themes: list[PulseTheme]
    quotes: list[PulseQuote]
    if cleaned and settings.groq_api_key:
        try:
            groq = GroqClient(settings)
            prompt = pulse_theme_prompt([n.text for n in cleaned])
            out = groq.chat_json(prompt=prompt)
            payload = json.loads(out) if out else {}
            themes = [PulseTheme.model_validate(t) for t in (payload.get("themes") or [])][:6]
            quotes = [PulseQuote.model_validate(q) for q in (payload.get("quotes") or [])][:8]
            if not themes:
                raise ValueError("empty_themes")
        except Exception as exc:
            degraded = True
            degraded_reason = f"groq_degraded:{type(exc).__name__}"
            themes, quotes = _rule_based_themes(cleaned)
    else:
        degraded = True
        degraded_reason = "groq_key_missing_or_no_reviews"
        themes, quotes = _rule_based_themes(cleaned)

    # Pulse synthesis (Gemini) with schema validation; fallback deterministic compose
    narrative = ""
    actions: list[str] = []
    if cleaned and settings.gemini_api_key:
        try:
            gemini = GeminiClient(settings)
            theme_json = json.dumps(
                {"themes": [t.model_dump() for t in themes], "quotes": [q.model_dump() for q in quotes]},
                ensure_ascii=False,
            )
            out = gemini.generate_text(weekly_pulse_prompt(theme_json))
            payload = json.loads(out) if out and out.strip().startswith("{") else {}
            narrative = str(payload.get("narrative") or "").strip()
            actions = [str(a) for a in (payload.get("recommended_actions") or [])][:6]
            if not narrative:
                raise ValueError("empty_narrative")
        except Exception as exc:
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

    avg = round(sum(r.rating for r in cleaned) / max(len(cleaned), 1), 2) if cleaned else 0.0
    metrics = PulseMetrics(reviews_considered=len(cleaned), average_rating=avg, lookback_weeks=req.lookback_weeks)

    pulse = WeeklyPulse(
        pulse_id=f"PULSE-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:8]}",
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
        "pulse_generated",
        extra={
            "correlation_id": "-",
            "degraded": degraded,
            "reviews_considered": metrics.reviews_considered,
        },
    )
    return pulse


async def get_current_pulse(settings: Settings) -> WeeklyPulse | None:
    return await get_pulse_repository(settings).get_current_pulse()


async def get_pulse_history(settings: Settings, limit: int = 20) -> list[WeeklyPulse]:
    return await get_pulse_repository(settings).get_pulse_history(limit=limit)
