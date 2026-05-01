"""Scheduler service — Phase 7.

Implements the internal scheduler-triggered weekly pulse send.

This is called by:
- POST /api/v1/internal/scheduler/pulse   (cron / manual trigger)
- POST /api/v1/pulse/send-now            (explicit user trigger)
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings
from app.mcp.send_weekly_pulse_email import send_weekly_pulse_email
from app.repositories.subscription_repository import get_subscription_repository
from app.schemas.pulse import SendNowResult
from app.services.pulse_workflow_service import get_current_pulse

logger = logging.getLogger(__name__)


async def send_latest_pulse_to_subscribers(
    *,
    settings: Settings,
    correlation_id: str | None,
) -> SendNowResult:
    """Send the latest persisted weekly pulse to all active subscribers."""
    pulse = await get_current_pulse(settings)
    pulse_id = pulse.pulse_id if pulse else "no-pulse"

    sub_repo = get_subscription_repository(settings)
    emails = await sub_repo.list_active()

    sent_to: list[str] = []
    for email in emails:
        try:
            result: dict[str, Any] = await send_weekly_pulse_email(
                pulse=pulse,
                to_email=email,
                correlation_id=correlation_id,
            )
            if result.get("status") == "sent":
                sent_to.append(email)
        except Exception as exc:
            logger.error(
                "weekly_pulse_send_unhandled_error",
                extra={"email": email, "pulse_id": pulse_id, "error": str(exc)},
            )

    logger.info(
        "weekly_pulse_send_complete",
        extra={"pulse_id": pulse_id, "subscribers": len(emails), "sent": len(sent_to)},
    )

    # Phase 7 keeps delivery synchronous; future phases may queue this work.
    return SendNowResult(sent_to=sent_to, pulse_id=pulse_id, status="sent" if sent_to else "queued")
