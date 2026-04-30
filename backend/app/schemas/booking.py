"""Booking schemas — Phase 5.

Single source of truth for booking states (Rules D3).
State machine matches Docs/Low Level Architecture.md §9.2.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class BookingStatus(str, Enum):
    """Canonical booking lifecycle states (Rules D3, W1).

    State machine (§9.2):
      draft → pending_advisor_approval | cancelled
      pending_advisor_approval → approved | rejected | cancelled
      approved → confirmation_sent | cancelled
      confirmation_sent → cancelled | completed
      rejected / cancelled / completed → (terminal)
    """

    DRAFT = "draft"
    COLLECTING_DETAILS = "collecting_details"
    PENDING_ADVISOR_APPROVAL = "pending_advisor_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONFIRMATION_SENT = "confirmation_sent"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


# Approved transitions per state (W1 — only via approved paths).
ALLOWED_TRANSITIONS: dict[BookingStatus, frozenset[BookingStatus]] = {
    BookingStatus.DRAFT: frozenset({
        BookingStatus.COLLECTING_DETAILS,
        BookingStatus.PENDING_ADVISOR_APPROVAL,
        BookingStatus.CANCELLED,
    }),
    BookingStatus.COLLECTING_DETAILS: frozenset({
        BookingStatus.PENDING_ADVISOR_APPROVAL,
        BookingStatus.CANCELLED,
    }),
    BookingStatus.PENDING_ADVISOR_APPROVAL: frozenset({
        BookingStatus.APPROVED,
        BookingStatus.REJECTED,
        BookingStatus.CANCELLED,
    }),
    BookingStatus.APPROVED: frozenset({
        BookingStatus.CONFIRMATION_SENT,
        BookingStatus.CANCELLED,
    }),
    BookingStatus.CONFIRMATION_SENT: frozenset({
        BookingStatus.CANCELLED,
        BookingStatus.COMPLETED,
    }),
    BookingStatus.REJECTED: frozenset(),
    BookingStatus.CANCELLED: frozenset(),
    BookingStatus.COMPLETED: frozenset(),
}

# States from which a booking may be cancelled (P5.5).
CANCELABLE_STATES: frozenset[BookingStatus] = frozenset({
    BookingStatus.DRAFT,
    BookingStatus.COLLECTING_DETAILS,
    BookingStatus.PENDING_ADVISOR_APPROVAL,
    BookingStatus.APPROVED,
    BookingStatus.CONFIRMATION_SENT,
})

# Terminal states — no outbound transitions.
TERMINAL_STATES: frozenset[BookingStatus] = frozenset({
    BookingStatus.REJECTED,
    BookingStatus.CANCELLED,
    BookingStatus.COMPLETED,
})


class BookingCreateRequest(BaseModel):
    """Customer-facing booking creation request (P5.1)."""

    session_id: str | None = Field(default=None, description="Linked chat session ID")
    customer_name: str = Field(min_length=1, max_length=200)
    customer_email: str = Field(min_length=3, max_length=320)
    issue_summary: str = Field(
        min_length=10,
        max_length=1000,
        description="Brief description of the advisory topic",
    )
    preferred_date: date = Field(description="Preferred session date (YYYY-MM-DD)")
    preferred_time: str = Field(
        pattern=r"^([01]\d|2[0-3]):([0-5]\d)$",
        description="Preferred time slot in HH:MM (24 h, IST)",
    )
    # Idempotency key sent by the client to prevent duplicate submissions (G9, D6).
    idempotency_key: str | None = Field(default=None, max_length=128)

    @field_validator("customer_email")
    @classmethod
    def email_basic_check(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("customer_email must be a valid email address")
        return v.strip().lower()


class BookingCancelRequest(BaseModel):
    """Cancel a booking by ID (P5.5)."""

    booking_id: str = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=500)


class BookingDetail(BaseModel):
    """Full booking detail returned to the client."""

    booking_id: str = Field(description="Collision-safe booking reference (BK-YYYYMMDD-XXXX)")
    session_id: str | None = None
    customer_name: str
    customer_email: str
    issue_summary: str
    preferred_date: str = Field(description="ISO date string YYYY-MM-DD")
    preferred_time: str = Field(description="HH:MM in 24 h format")
    status: BookingStatus
    created_at: datetime = Field(description="UTC timestamp of creation")
    updated_at: datetime = Field(description="UTC timestamp of last update")
    display_timezone: str = Field(
        description="Timezone label shown to the user (UI13 — always visible)"
    )
    cancellation_reason: str | None = None
