"""Weekly Pulse schemas (Phase 2)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


DeviceType = Literal["Phone", "Chromebook", "Tablet", "Unknown"]


class RawReview(BaseModel):
    """Raw persisted record from Playwright capture (no PII)."""

    source: Literal["playstore"] = "playstore"
    review_id: str
    rating: int = Field(ge=1, le=5)
    text: str
    review_date: date | None = None
    found_review_helpful: int | None = Field(default=None, ge=0)
    device: DeviceType = "Unknown"
    collected_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class NormalizedReview(BaseModel):
    """Cleaned and normalized review row used for theme/pulse generation."""

    review_id: str
    rating: int = Field(ge=1, le=5)
    text: str
    review_date: date | None = None
    found_review_helpful: int | None = Field(default=None, ge=0)
    device: DeviceType = "Unknown"
    content_hash: str
    normalized_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class PulseTheme(BaseModel):
    theme: str
    summary: str
    count: int = Field(ge=0)


class PulseQuote(BaseModel):
    review_id: str
    quote: str
    rating: int = Field(ge=1, le=5)


class PulseMetrics(BaseModel):
    reviews_considered: int = Field(ge=0)
    average_rating: float = Field(ge=0, le=5)
    lookback_weeks: int = Field(ge=1, le=8)


class WeeklyPulse(BaseModel):
    pulse_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    metrics: PulseMetrics
    themes: list[PulseTheme]
    quotes: list[PulseQuote]
    recommended_actions: list[str]
    narrative: str
    degraded: bool = False
    degraded_reason: str | None = None


class PulseGenerateRequest(BaseModel):
    lookback_weeks: int = Field(default=8, ge=1, le=8)
    use_fixture: bool = False


class SubscribeRequest(BaseModel):
    email: EmailStr


class SubscribeResult(BaseModel):
    email: str
    status: Literal["subscribed", "unsubscribed"]
    updated_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class SendNowResult(BaseModel):
    sent_to: list[str]
    pulse_id: str
    status: str
