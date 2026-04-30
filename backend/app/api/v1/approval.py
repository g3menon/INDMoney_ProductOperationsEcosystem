"""Approval APIs — Phase 6.

Routes:
  POST /api/v1/approval/{approval_id}/approve   Approve a booking (approval_id = booking_id)
  POST /api/v1/approval/{approval_id}/reject    Reject a booking

These endpoints expose the same approval_workflow_service as the /advisor routes
but use the architecture-spec path prefix (/approval/{approval_id}/…).
approval_id is the booking_id — no separate approvals table is needed (Phase 5
bookings + booking_events tables are sufficient to track approval state).

See backend/app/api/v1/advisor.py for the primary advisor-facing surface.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.core.config import get_settings
from app.repositories.booking_repository import get_booking_repository
from app.schemas.advisor import ApprovalResult, ApproveRequest, RejectRequest
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

router = APIRouter(prefix="/approval")


# ────────────────────────────────────────────────────────────────────
# POST /approval/{approval_id}/approve
# ────────────────────────────────────────────────────────────────────


@router.post("/{approval_id}/approve", response_model=APIEnvelope[ApprovalResult])
async def approve_via_approval_route(
    approval_id: str,
    body: ApproveRequest,
) -> APIEnvelope[ApprovalResult]:
    """Approve a booking via the /approval/{approval_id}/approve path.

    approval_id is the booking_id.  Delegates to the same approval_workflow_service
    used by POST /advisor/approve/{booking_id}.

    Idempotent: already-approved booking returns 200, idempotent=True (P6.3, G9).
    """
    settings = get_settings()
    repo = get_booking_repository(settings)
    actor = "advisor"

    try:
        updated, idempotent = await approve_booking(
            booking_id=approval_id,
            reason=body.reason,
            actor=actor,
            repo=repo,
        )
    except ApprovalBookingNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "booking_not_found", "message": f"Booking {approval_id!r} not found."},
        )
    except ApprovalAlreadyRejectedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "booking_already_rejected",
                "message": (
                    f"Booking {approval_id!r} has already been rejected and cannot be approved."
                ),
            },
        )
    except ApprovalNotPendingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "approval_invalid_transition",
                "message": (
                    f"Booking {approval_id!r} cannot be approved from its current state: "
                    f"'{exc.booking.status.value}'."
                ),
            },
        )

    prev_status = updated.status.value if idempotent else BookingStatus.PENDING_ADVISOR_APPROVAL.value

    return APIEnvelope(
        success=True,
        message="booking_approved_idempotent" if idempotent else "booking_approved",
        data=ApprovalResult(
            booking_id=approval_id,
            previous_status=prev_status,
            new_status=updated.status.value,
            idempotent=idempotent,
            booking=updated,
        ),
        errors=(
            [ErrorDetail(code="approval_already_approved", message="Already approved.", detail=approval_id)]
            if idempotent
            else []
        ),
    )


# ────────────────────────────────────────────────────────────────────
# POST /approval/{approval_id}/reject
# ────────────────────────────────────────────────────────────────────


@router.post("/{approval_id}/reject", response_model=APIEnvelope[ApprovalResult])
async def reject_via_approval_route(
    approval_id: str,
    body: RejectRequest,
) -> APIEnvelope[ApprovalResult]:
    """Reject a booking via the /approval/{approval_id}/reject path.

    Idempotent: already-rejected booking returns 200, idempotent=True (P6.3, G9).
    """
    settings = get_settings()
    repo = get_booking_repository(settings)
    actor = "advisor"

    try:
        updated, idempotent = await reject_booking(
            booking_id=approval_id,
            reason=body.reason,
            actor=actor,
            repo=repo,
        )
    except ApprovalBookingNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "booking_not_found", "message": f"Booking {approval_id!r} not found."},
        )
    except ApprovalAlreadyApprovedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "booking_already_approved",
                "message": (
                    f"Booking {approval_id!r} has already been approved and cannot be rejected."
                ),
            },
        )
    except ApprovalNotPendingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "approval_invalid_transition",
                "message": (
                    f"Booking {approval_id!r} cannot be rejected from its current state: "
                    f"'{exc.booking.status.value}'."
                ),
            },
        )

    prev_status = updated.status.value if idempotent else BookingStatus.PENDING_ADVISOR_APPROVAL.value

    return APIEnvelope(
        success=True,
        message="booking_rejected_idempotent" if idempotent else "booking_rejected",
        data=ApprovalResult(
            booking_id=approval_id,
            previous_status=prev_status,
            new_status=updated.status.value,
            idempotent=idempotent,
            booking=updated,
        ),
        errors=(
            [ErrorDetail(code="approval_already_rejected", message="Already rejected.", detail=approval_id)]
            if idempotent
            else []
        ),
    )
