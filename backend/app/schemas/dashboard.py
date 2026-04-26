"""Dashboard / badges schemas (`Docs/Architecture.md` — Badge architecture)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CustomerBadges(BaseModel):
    booking_in_progress: int = 0
    follow_up_available: int = 0
    voice_ready: bool = False


class ProductBadges(BaseModel):
    pulse_ready: bool = False
    active_subscribers: int = 0
    next_scheduled_send_ist: str | None = None
    send_failure_warning: bool = False


class AdvisorBadges(BaseModel):
    pending_approvals: int = 0
    upcoming_bookings_today: int = 0
    recently_rejected: int = 0
    cancellations_to_review: int = 0


class BadgePayload(BaseModel):
    customer: CustomerBadges
    product: ProductBadges
    advisor: AdvisorBadges
    supabase_connected: bool = Field(
        description="True when the backend verified Supabase reachability for this request.",
    )
