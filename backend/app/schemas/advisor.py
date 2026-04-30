"""Advisor schemas — Phase 6.

Request and response models for the HITL advisor approval workflow.
Follows the single-source-of-truth principle (Rules D3, G13).
All responses use APIEnvelope[T] at the API layer.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.booking import BookingDetail


# ── Request bodies ────────────────────────────────────────────────────────────


class ApproveRequest(BaseModel):
    """Body for POST /advisor/approve/{booking_id}."""

    reason: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional approval note stored in the booking_events audit trail (P6.5)",
    )


class RejectRequest(BaseModel):
    """Body for POST /advisor/reject/{booking_id}.

    Reason is required for rejection to ensure the audit trail is actionable (P6.5).
    """

    reason: str = Field(
        min_length=1,
        max_length=1000,
        description="Required rejection reason stored in the booking_events audit trail (P6.5)",
    )


# ── Response payloads ─────────────────────────────────────────────────────────


class AdvisorBookingItem(BaseModel):
    """Concise booking summary for the advisor pending/upcoming lists (P6.2).

    Returns only the fields the advisor needs to scan and act on.
    Raw payloads or full chat history are never surfaced here.
    """

    booking_id: str
    customer_name: str
    issue_summary: str
    preferred_date: str = Field(description="ISO date YYYY-MM-DD")
    preferred_time: str = Field(description="HH:MM (24 h, IST)")
    status: str
    display_timezone: str
    created_at: str = Field(description="ISO UTC timestamp")

    @classmethod
    def from_booking_detail(cls, b: BookingDetail) -> "AdvisorBookingItem":
        return cls(
            booking_id=b.booking_id,
            customer_name=b.customer_name,
            issue_summary=b.issue_summary,
            preferred_date=b.preferred_date,
            preferred_time=b.preferred_time,
            status=b.status.value,
            display_timezone=b.display_timezone,
            created_at=b.created_at.isoformat(),
        )


class PendingApprovalList(BaseModel):
    """Response payload for GET /advisor/pending."""

    items: list[AdvisorBookingItem]
    count: int


class UpcomingBookingList(BaseModel):
    """Response payload for GET /advisor/upcoming.

    Upcoming = bookings in APPROVED or CONFIRMATION_SENT states.
    """

    items: list[AdvisorBookingItem]
    count: int


class ApprovalResult(BaseModel):
    """Result of an approve or reject action.

    idempotent=True means the booking was already in the target state;
    no state write occurred.  The current booking is always returned so
    the client can reconcile (Rules P6.3, G9, W2).
    """

    booking_id: str
    previous_status: str
    new_status: str
    idempotent: bool = Field(
        default=False,
        description="True when booking was already in the target state; no write occurred",
    )
    booking: BookingDetail
