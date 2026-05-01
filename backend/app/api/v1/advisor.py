"""Advisor APIs — Phase 6.

Routes:
  GET  /api/v1/advisor/pending             List bookings pending advisor approval
  GET  /api/v1/advisor/upcoming            List approved / confirmation-sent bookings
  POST /api/v1/advisor/approve/{booking_id}  Approve a booking
  POST /api/v1/advisor/reject/{booking_id}   Reject a booking

All responses use APIEnvelope[T] (Docs/Low Level Architecture.md §6.2).
Errors are user-safe: no stack traces, no raw DB details (G7, Rules UI4).

Idempotency contract (P6.3, G9):
  - Approving an already-approved booking → 200 OK, idempotent=True, no re-write.
  - Rejecting an already-rejected booking → 200 OK, idempotent=True, no re-write.
  - Approving a rejected booking          → 409 Conflict.
  - Rejecting an approved booking         → 409 Conflict.
  - Acting on a booking in cancelled/completed state → 422 Unprocessable.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.core.config import get_settings
from app.repositories.booking_repository import get_booking_repository
from app.schemas.advisor import (
    AdvisorBookingItem,
    ApprovalResult,
    ApproveRequest,
    PendingApprovalList,
    RejectRequest,
    UpcomingBookingList,
)
from app.schemas.booking import BookingStatus
from app.schemas.common import APIEnvelope, ErrorDetail
from app.services.approval_workflow_service import (
    ApprovalAlreadyApprovedError,
    ApprovalAlreadyRejectedError,
    ApprovalBookingNotFoundError,
    ApprovalNotPendingError,
    approve_booking,
    reject_booking,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/advisor")

# Upcoming = sessions the advisor has accepted; these are scheduled to happen.
_UPCOMING_STATUSES = [BookingStatus.APPROVED, BookingStatus.CONFIRMATION_SENT]


# ────────────────────────────────────────────────────────────────────
# GET /advisor/pending
# ────────────────────────────────────────────────────────────────────


@router.get("/pending", response_model=APIEnvelope[PendingApprovalList])
async def list_pending_approvals() -> APIEnvelope[PendingApprovalList]:
    """Return all bookings in the 'pending_advisor_approval' state.

    This is the primary feed for the Advisor tab's pending queue.
    Items are ordered by creation time (oldest first via repository).
    """
    settings = get_settings()
    repo = get_booking_repository(settings)

    bookings = await repo.list_by_status(BookingStatus.PENDING_ADVISOR_APPROVAL)
    items = [AdvisorBookingItem.from_booking_detail(b) for b in bookings]

    logger.info("advisor_pending_list_fetched", extra={"count": len(items)})

    return APIEnvelope(
        success=True,
        message="pending_approvals",
        data=PendingApprovalList(items=items, count=len(items)),
    )


# ────────────────────────────────────────────────────────────────────
# GET /advisor/upcoming
# ────────────────────────────────────────────────────────────────────


@router.get("/upcoming", response_model=APIEnvelope[UpcomingBookingList])
async def list_upcoming_bookings() -> APIEnvelope[UpcomingBookingList]:
    """Return bookings in APPROVED or CONFIRMATION_SENT state.

    These are sessions the advisor has accepted and that are either awaiting
    the confirmation email send (Phase 7) or already confirmed.
    """
    settings = get_settings()
    repo = get_booking_repository(settings)

    bookings = await repo.list_by_statuses(_UPCOMING_STATUSES)
    items = [AdvisorBookingItem.from_booking_detail(b) for b in bookings]

    logger.info("advisor_upcoming_list_fetched", extra={"count": len(items)})

    return APIEnvelope(
        success=True,
        message="upcoming_bookings",
        data=UpcomingBookingList(items=items, count=len(items)),
    )


# ────────────────────────────────────────────────────────────────────
# POST /advisor/approve/{booking_id}
# ────────────────────────────────────────────────────────────────────


@router.post("/approve/{booking_id}", response_model=APIEnvelope[ApprovalResult])
async def approve_booking_route(
    booking_id: str,
    body: ApproveRequest,
) -> APIEnvelope[ApprovalResult]:
    """Approve a booking.

    Idempotent: approving an already-approved booking returns 200 with
    idempotent=True — no duplicate state write or event (P6.3, G9).

    Returns 404 if the booking does not exist.
    Returns 409 if the booking is already rejected (cannot approve a rejected booking).
    Returns 422 if the booking is in a non-approvable terminal state (cancelled, completed).
    """
    settings = get_settings()
    repo = get_booking_repository(settings)

    # Actor defaults to "advisor" for Phase 6; Phase 7 can pass the authenticated user.
    actor = body.actor

    try:
        updated, idempotent = await approve_booking(
            booking_id=booking_id,
            reason=body.reason,
            actor=actor,
            repo=repo,
        )
    except ApprovalBookingNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "booking_not_found", "message": f"Booking {booking_id!r} not found."},
        )
    except ApprovalAlreadyRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "booking_already_rejected",
                "message": (
                    f"Booking {booking_id!r} has already been rejected and cannot be approved. "
                    "Current status: 'rejected'."
                ),
            },
        )
    except ApprovalNotPendingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "approval_invalid_transition",
                "message": (
                    f"Booking {booking_id!r} cannot be approved from its current state: "
                    f"'{exc.booking.status.value}'."
                ),
            },
        )

    prev_status = updated.status.value if idempotent else BookingStatus.PENDING_ADVISOR_APPROVAL.value

    return APIEnvelope(
        success=True,
        message="booking_approved_idempotent" if idempotent else "booking_approved",
        data=ApprovalResult(
            booking_id=booking_id,
            previous_status=prev_status,
            new_status=updated.status.value,
            idempotent=idempotent,
            booking=updated,
        ),
        errors=(
            [
                ErrorDetail(
                    code="approval_already_approved",
                    message="Booking was already approved; no change made.",
                    detail=booking_id,
                )
            ]
            if idempotent
            else []
        ),
    )


# ────────────────────────────────────────────────────────────────────
# POST /advisor/reject/{booking_id}
# ────────────────────────────────────────────────────────────────────


@router.post("/reject/{booking_id}", response_model=APIEnvelope[ApprovalResult])
async def reject_booking_route(
    booking_id: str,
    body: RejectRequest,
) -> APIEnvelope[ApprovalResult]:
    """Reject a booking.

    Idempotent: rejecting an already-rejected booking returns 200 with
    idempotent=True — no duplicate state write or event (P6.3, G9).

    Returns 404 if the booking does not exist.
    Returns 409 if the booking is already approved (cannot reject an approved booking).
    Returns 422 if the booking is in a non-rejectable terminal state (cancelled, completed).
    """
    settings = get_settings()
    repo = get_booking_repository(settings)

    actor = body.actor

    try:
        updated, idempotent = await reject_booking(
            booking_id=booking_id,
            reason=body.reason,
            actor=actor,
            repo=repo,
        )
    except ApprovalBookingNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "booking_not_found", "message": f"Booking {booking_id!r} not found."},
        )
    except ApprovalAlreadyApprovedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "booking_already_approved",
                "message": (
                    f"Booking {booking_id!r} has already been approved and cannot be rejected. "
                    "Current status: 'approved'."
                ),
            },
        )
    except ApprovalNotPendingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "approval_invalid_transition",
                "message": (
                    f"Booking {booking_id!r} cannot be rejected from its current state: "
                    f"'{exc.booking.status.value}'."
                ),
            },
        )

    prev_status = updated.status.value if idempotent else BookingStatus.PENDING_ADVISOR_APPROVAL.value

    return APIEnvelope(
        success=True,
        message="booking_rejected_idempotent" if idempotent else "booking_rejected",
        data=ApprovalResult(
            booking_id=booking_id,
            previous_status=prev_status,
            new_status=updated.status.value,
            idempotent=idempotent,
            booking=updated,
        ),
        errors=(
            [
                ErrorDetail(
                    code="approval_already_rejected",
                    message="Booking was already rejected; no change made.",
                    detail=booking_id,
                )
            ]
            if idempotent
            else []
        ),
    )
