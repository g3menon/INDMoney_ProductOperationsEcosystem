"""Approval workflow service — Phase 6.

Implements the advisor HITL approve / reject workflow.

Design decisions:
- No separate "approvals" table is created.  The bookings table (status column)
  and booking_events (audit log) are sufficient to track approval state (Phase 5
  already created both tables).  See infra/supabase/phase6_schema.sql for the
  rationale note.
- Both approve_booking and reject_booking are idempotent: re-calling them when
  the booking is already in the target state returns the current booking without
  writing a duplicate event (Rules P6.3, G9).
- Side-effect stubs (Gmail, Calendar, Sheets) are left as Phase 7 TODOs at the
  exact point they would be triggered, keeping the boundary explicit (P6.6).

Rules satisfied:
  P6.1 — Human approval is authoritative and traceable.
  P6.3 — Idempotent: double-click/retry is safe.
  P6.4 — Shared state updated via the single booking repo (W2).
  P6.5 — Audit trail: actor + reason persisted in booking_events.
  P6.6 — Phase 7 integration stubs at the correct insertion point.
  W1   — State changes only via ALLOWED_TRANSITIONS.
  G9   — Idempotent writes.
  O2   — Structured transition logs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.repositories.booking_repository import BookingRepository
from app.schemas.booking import ALLOWED_TRANSITIONS, BookingDetail, BookingStatus

logger = logging.getLogger(__name__)


# ── Domain exceptions ─────────────────────────────────────────────────────────


class ApprovalBookingNotFoundError(Exception):
    """Raised when the target booking does not exist."""

    def __init__(self, booking_id: str) -> None:
        super().__init__(f"Booking {booking_id!r} not found")
        self.booking_id = booking_id


class ApprovalAlreadyApprovedError(Exception):
    """Idempotent signal: booking is already APPROVED.

    Raised when reject is attempted on an already-approved booking.
    The caller (API layer) returns 409 with the current state.
    """

    def __init__(self, booking: BookingDetail) -> None:
        super().__init__(f"Booking {booking.booking_id!r} is already approved")
        self.booking = booking


class ApprovalAlreadyRejectedError(Exception):
    """Idempotent signal: booking is already REJECTED.

    Raised when approve is attempted on an already-rejected booking.
    """

    def __init__(self, booking: BookingDetail) -> None:
        super().__init__(f"Booking {booking.booking_id!r} is already rejected")
        self.booking = booking


class ApprovalNotPendingError(Exception):
    """Booking is not in a state that allows approve/reject (e.g. cancelled, completed).

    Raised when the requested transition is not present in ALLOWED_TRANSITIONS.
    """

    def __init__(self, booking: BookingDetail, target: BookingStatus) -> None:
        super().__init__(
            f"Booking {booking.booking_id!r}: cannot transition "
            f"{booking.status.value!r} → {target.value!r}"
        )
        self.booking = booking
        self.target = target


# ── Helpers ───────────────────────────────────────────────────────────────────


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── Service functions ─────────────────────────────────────────────────────────


async def approve_booking(
    *,
    booking_id: str,
    reason: str | None,
    actor: str,
    repo: BookingRepository,
) -> tuple[BookingDetail, bool]:
    """Approve a pending booking.

    Returns:
        (updated_booking, idempotent)

        idempotent=True  → booking was already APPROVED; no write occurred (P6.3).
        idempotent=False → transition was applied and audited.

    Raises:
        ApprovalBookingNotFoundError  — booking_id does not exist.
        ApprovalAlreadyRejectedError  — booking is in REJECTED state; cannot approve.
        ApprovalNotPendingError       — booking is in a non-approvable terminal state.
    """
    booking = await repo.get_by_id(booking_id)
    if booking is None:
        raise ApprovalBookingNotFoundError(booking_id)

    # Idempotent path: already approved → return current state without re-writing (P6.3, G9).
    if booking.status == BookingStatus.APPROVED:
        logger.info(
            "approval_already_approved_idempotent",
            extra={"booking_id": booking_id, "actor": actor},
        )
        return booking, True

    # Guard transitions that the state machine forbids (W1).
    allowed = ALLOWED_TRANSITIONS.get(booking.status, frozenset())
    if BookingStatus.APPROVED not in allowed:
        if booking.status == BookingStatus.REJECTED:
            raise ApprovalAlreadyRejectedError(booking)
        raise ApprovalNotPendingError(booking, BookingStatus.APPROVED)

    now = _now_utc()
    updated = await repo.update_status(
        booking_id=booking_id,
        new_status=BookingStatus.APPROVED,
        updated_at=now,
        actor=actor,
    )

    logger.info(
        "booking_approved",
        extra={
            "booking_id": booking_id,
            "from_status": booking.status.value,
            "actor": actor,
            "reason": reason,
        },
    )

    # ── Phase 7 integration stubs ────────────────────────────────────────────
    # TODO Phase 7: await mcp.send_booking_confirmation(booking=updated, actor=actor)
    # TODO Phase 7: await mcp.create_calendar_hold(booking=updated, actor=actor)
    # TODO Phase 7: await mcp.append_advisor_sheet_row(booking=updated)
    # ────────────────────────────────────────────────────────────────────────

    return updated, False


async def reject_booking(
    *,
    booking_id: str,
    reason: str,
    actor: str,
    repo: BookingRepository,
) -> tuple[BookingDetail, bool]:
    """Reject a pending booking.

    Returns:
        (updated_booking, idempotent)

        idempotent=True  → booking was already REJECTED; no write occurred (P6.3).
        idempotent=False → transition was applied and audited.

    Raises:
        ApprovalBookingNotFoundError  — booking_id does not exist.
        ApprovalAlreadyApprovedError  — booking is already APPROVED; cannot reject.
        ApprovalNotPendingError       — booking is in a non-rejectable terminal state.
    """
    booking = await repo.get_by_id(booking_id)
    if booking is None:
        raise ApprovalBookingNotFoundError(booking_id)

    # Idempotent path: already rejected → return current state (P6.3, G9).
    if booking.status == BookingStatus.REJECTED:
        logger.info(
            "approval_already_rejected_idempotent",
            extra={"booking_id": booking_id, "actor": actor},
        )
        return booking, True

    # Guard transitions that the state machine forbids (W1).
    allowed = ALLOWED_TRANSITIONS.get(booking.status, frozenset())
    if BookingStatus.REJECTED not in allowed:
        if booking.status == BookingStatus.APPROVED:
            raise ApprovalAlreadyApprovedError(booking)
        raise ApprovalNotPendingError(booking, BookingStatus.REJECTED)

    now = _now_utc()
    updated = await repo.update_status(
        booking_id=booking_id,
        new_status=BookingStatus.REJECTED,
        updated_at=now,
        cancellation_reason=reason,
        actor=actor,
    )

    logger.info(
        "booking_rejected",
        extra={
            "booking_id": booking_id,
            "from_status": booking.status.value,
            "actor": actor,
            "reason": reason,
        },
    )

    return updated, False
