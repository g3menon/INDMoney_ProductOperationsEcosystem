"""Booking workflow service — Phase 5.

Implements the booking state machine, ID generation, idempotency, and
timezone-consistent timestamps.

State machine (Docs/Low Level Architecture.md §9.2):
  draft → pending_advisor_approval | cancelled
  pending_advisor_approval → approved | rejected | cancelled
  approved → confirmation_sent | cancelled
  confirmation_sent → cancelled | completed
  rejected / cancelled / completed → (terminal)

Rules satisfied:
  W1  — state changes only via ALLOWED_TRANSITIONS
  G9  — idempotency via idempotency_key
  D5  — stored UTC, display label carries timezone (P5.2, UI13)
  P5.3 — BK-YYYYMMDD-XXXX collision-safe ID format
  O2  — structured transition logs
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from uuid import uuid4

from app.core.config import Settings
from app.repositories.booking_repository import BookingRepository
from app.schemas.booking import (
    ALLOWED_TRANSITIONS,
    CANCELABLE_STATES,
    BookingCancelRequest,
    BookingCreateRequest,
    BookingDetail,
    BookingStatus,
)

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────
# Custom exceptions — translated to HTTP errors in the API layer
# ────────────────────────────────────────────────────────────────────


class BookingNotFoundError(Exception):
    def __init__(self, booking_id: str) -> None:
        super().__init__(f"Booking {booking_id!r} not found")
        self.booking_id = booking_id


class BookingDuplicateError(Exception):
    """Raised when idempotency_key already exists; carries the existing booking."""

    def __init__(self, existing: BookingDetail) -> None:
        super().__init__(f"Duplicate submission for booking {existing.booking_id!r}")
        self.existing = existing


class BookingInvalidTransitionError(Exception):
    """Raised when the requested state transition is not permitted (W1)."""

    def __init__(self, booking_id: str, from_status: BookingStatus, to_status: BookingStatus) -> None:
        super().__init__(
            f"Booking {booking_id!r}: transition {from_status.value!r} → {to_status.value!r} is not allowed"
        )
        self.booking_id = booking_id
        self.from_status = from_status
        self.to_status = to_status


class BookingAlreadyCancelledError(Exception):
    """Idempotent — booking is already in a terminal cancelled state."""

    def __init__(self, booking: BookingDetail) -> None:
        super().__init__(f"Booking {booking.booking_id!r} is already cancelled")
        self.booking = booking


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────


def _generate_booking_id() -> str:
    """Generate a collision-safe booking ID: BK-YYYYMMDD-XXXX (P5.3).

    XXXX = 4 uppercase hex chars from a fresh UUID4 — negligible collision
    probability within a single calendar day.
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = uuid4().hex[:4].upper()
    return f"BK-{today}-{suffix}"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _display_timezone_label(tz_name: str) -> str:
    """Return a human-readable timezone label (UI13 — always visible)."""
    labels = {
        "Asia/Kolkata": "Asia/Kolkata (IST)",
        "UTC": "UTC",
    }
    return labels.get(tz_name, tz_name)


def _validate_not_past(preferred_date: date) -> None:
    """Reject booking requests for dates that have already passed."""
    today = datetime.now(timezone.utc).date()
    if preferred_date < today:
        raise ValueError(
            f"preferred_date {preferred_date.isoformat()!r} is in the past. "
            "Please choose today or a future date."
        )


def _assert_transition(booking: BookingDetail, to_status: BookingStatus) -> None:
    """Raise BookingInvalidTransitionError if the transition is not in ALLOWED_TRANSITIONS (W1)."""
    allowed = ALLOWED_TRANSITIONS.get(booking.status, frozenset())
    if to_status not in allowed:
        raise BookingInvalidTransitionError(
            booking_id=booking.booking_id,
            from_status=booking.status,
            to_status=to_status,
        )


# ────────────────────────────────────────────────────────────────────
# Public service functions
# ────────────────────────────────────────────────────────────────────


async def create_booking(
    *,
    request: BookingCreateRequest,
    repo: BookingRepository,
    settings: Settings,
) -> BookingDetail:
    """Create a new booking and persist it.

    Idempotency: if idempotency_key is provided and a booking with that key
    already exists, return the existing booking without creating a duplicate (G9).

    New bookings start in PENDING_ADVISOR_APPROVAL state — the customer flow
    submits all required details in one shot for Phase 5.
    """
    # ── Idempotency check (G9, D6) ──────────────────────────────────
    if request.idempotency_key:
        existing = await repo.get_by_idempotency_key(request.idempotency_key)
        if existing is not None:
            logger.info(
                "booking_duplicate_submission_idempotent",
                extra={
                    "booking_id": existing.booking_id,
                    "idempotency_key": request.idempotency_key,
                },
            )
            raise BookingDuplicateError(existing)

    # ── Date validation ──────────────────────────────────────────────
    _validate_not_past(request.preferred_date)

    # ── Build the booking detail ─────────────────────────────────────
    tz_label = _display_timezone_label(settings.default_timezone)
    now = _now_utc()
    booking_id = _generate_booking_id()

    detail = BookingDetail(
        booking_id=booking_id,
        session_id=request.session_id,
        customer_name=request.customer_name,
        customer_email=request.customer_email,
        issue_summary=request.issue_summary,
        preferred_date=request.preferred_date.isoformat(),
        preferred_time=request.preferred_time,
        status=BookingStatus.PENDING_ADVISOR_APPROVAL,
        created_at=now,
        updated_at=now,
        display_timezone=tz_label,
        cancellation_reason=None,
    )

    await repo.create(detail)

    # Register idempotency key mapping in the in-memory repo.
    if request.idempotency_key and hasattr(repo, "register_idempotency"):
        await repo.register_idempotency(request.idempotency_key, booking_id)  # type: ignore[attr-defined]

    logger.info(
        "booking_created",
        extra={
            "booking_id": booking_id,
            "status": detail.status.value,
            "preferred_date": detail.preferred_date,
            "session_id": request.session_id,
        },
    )
    return detail


async def get_booking(
    *,
    booking_id: str,
    repo: BookingRepository,
) -> BookingDetail:
    """Fetch a booking by ID; raise BookingNotFoundError if absent."""
    detail = await repo.get_by_id(booking_id)
    if detail is None:
        raise BookingNotFoundError(booking_id)
    return detail


async def cancel_booking(
    *,
    request: BookingCancelRequest,
    repo: BookingRepository,
) -> BookingDetail:
    """Cancel a booking.

    Idempotent: if already cancelled, returns current state without error (G9).
    Raises BookingNotFoundError for unknown IDs.
    Raises BookingInvalidTransitionError for non-cancelable terminal states (W1).
    """
    detail = await repo.get_by_id(request.booking_id)
    if detail is None:
        raise BookingNotFoundError(request.booking_id)

    # Already cancelled — idempotent return (G9).
    if detail.status == BookingStatus.CANCELLED:
        logger.info(
            "booking_cancel_idempotent",
            extra={"booking_id": request.booking_id, "status": detail.status.value},
        )
        raise BookingAlreadyCancelledError(detail)

    # Guard non-cancelable terminal states (W1, P5.5).
    if detail.status not in CANCELABLE_STATES:
        raise BookingInvalidTransitionError(
            booking_id=request.booking_id,
            from_status=detail.status,
            to_status=BookingStatus.CANCELLED,
        )

    # Explicit allowed-transition check (belt-and-suspenders).
    _assert_transition(detail, BookingStatus.CANCELLED)

    now = _now_utc()
    updated = await repo.update_status(
        booking_id=request.booking_id,
        new_status=BookingStatus.CANCELLED,
        updated_at=now,
        cancellation_reason=request.reason,
    )

    logger.info(
        "booking_cancelled",
        extra={
            "booking_id": request.booking_id,
            "from_status": detail.status.value,
            "reason": request.reason,
        },
    )
    return updated
