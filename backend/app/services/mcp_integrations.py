"""MCP integrations coordinator — Phase 7.

Wires the three post-approval governed side effects together and is called
from approval_workflow_service.py at the Phase 7 insertion point.

Execution contract:
  1. Fetch a Google OAuth access token once (shared across all three calls).
  2. Run Gmail → Calendar → Sheets in sequence.
  3. Each integration is wrapped in its own try/except so a failure in one
     does NOT prevent the others from attempting (Rules I5, W5).
  4. Booking state is NEVER touched here — callers are responsible for
     persisting the approval before calling this function (W3).
  5. All results (success, skip, or failure) are logged. The final summary
     log carries all three outcomes in one structured event.

Rules satisfied:
  I1  — all external writes flow through dedicated service modules.
  I3  — side effects are approval-gated (caller guarantees this).
  I5  — each integration degrades independently.
  W3  — approval state committed before this function is called.
  W5  — partial failure preserves workflow truth; approval is not rolled back.
  G7  — failures are logged and returned; never re-raised to the approval flow.
  G8  — structured logs with booking_id at every step.
  G9  — each integration module is responsible for its own idempotency notes.
"""

from __future__ import annotations

import logging
from typing import Any

from app.repositories.token_repository import get_google_oauth_token
from app.schemas.booking import BookingDetail
from app.services.calendar_service import create_calendar_hold
from app.services.gmail_service import send_booking_confirmation
from app.services.sheets_service import append_advisor_sheet_row

logger = logging.getLogger(__name__)


async def run_approval_integrations(
    *,
    booking: BookingDetail,
    actor: str,
) -> None:
    """Execute Gmail, Calendar, and Sheets side effects after a booking approval.

    This function always returns None — integration results are communicated
    exclusively through structured logs. The approval state machine must not
    be affected by integration outcomes.

    Args:
        booking: The BookingDetail in APPROVED state.
        actor:   Identifier of the advisor who performed the approval (for logs).
    """
    booking_id = booking.booking_id

    # ── 1. Obtain a live OAuth access token (shared across all three calls) ──
    access_token: str | None = await get_google_oauth_token()

    # ── 2. Gmail — send booking confirmation email ────────────────────────────
    gmail_result: dict[str, Any] = {"status": "not_attempted"}
    try:
        gmail_result = send_booking_confirmation(
            booking=booking,
            access_token=access_token,
        )
    except Exception as exc:
        logger.error(
            "gmail_confirmation_unhandled_error",
            extra={"booking_id": booking_id, "actor": actor, "error": str(exc)},
        )
        gmail_result = {"status": "failed", "reason": str(exc)}

    # ── 3. Calendar — create calendar hold ───────────────────────────────────
    calendar_result: dict[str, Any] = {"status": "not_attempted"}
    try:
        calendar_result = create_calendar_hold(
            booking=booking,
            access_token=access_token,
        )
    except Exception as exc:
        logger.error(
            "calendar_hold_unhandled_error",
            extra={"booking_id": booking_id, "actor": actor, "error": str(exc)},
        )
        calendar_result = {"status": "failed", "reason": str(exc)}

    # ── 4. Sheets — append advisor export row ─────────────────────────────────
    sheets_result: dict[str, Any] = {"status": "not_attempted"}
    try:
        sheets_result = append_advisor_sheet_row(
            booking=booking,
            access_token=access_token,
        )
    except Exception as exc:
        logger.error(
            "sheets_row_unhandled_error",
            extra={"booking_id": booking_id, "actor": actor, "error": str(exc)},
        )
        sheets_result = {"status": "failed", "reason": str(exc)}

    # ── 5. Summary log — all three outcomes in one structured event ───────────
    logger.info(
        "approval_integrations_complete",
        extra={
            "booking_id": booking_id,
            "actor": actor,
            "gmail": gmail_result,
            "calendar": calendar_result,
            "sheets": sheets_result,
        },
    )
