"""Gmail integration service — Phase 7.

Sends a plain-text booking confirmation email to the customer when a booking
is approved by the advisor.

Email spec (Phase 7):
  Subject : "Your advisory session has been confirmed — {preferred_date} at {preferred_time}"
  Body    : customer name, issue summary, preferred date/time, advisor name
  Format  : plain text (HTML template is Phase 8)

Rules satisfied:
  I1  — external write goes through this dedicated integration module only.
  I2  — OAuth credentials stay server-side; access token is passed in.
  I5  — graceful degradation: returns a skip result when unconfigured.
  G5  — no secrets in code; all IDs come from Settings.
  G7  — known failure modes produce safe results; never raises to the caller.
  O2  — structured log on success; caller logs the result.
"""

from __future__ import annotations

import base64
import email as email_lib
import logging
from email.mime.text import MIMEText
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from app.core.config import get_settings
from app.schemas.booking import BookingDetail

logger = logging.getLogger(__name__)

# ── Internal result shapes ────────────────────────────────────────────────────

_SKIP = "skipped"
_SENT = "sent"
_FAILED = "failed"


def _build_email_body(booking: BookingDetail, advisor_name: str) -> str:
    return (
        f"Dear {booking.customer_name},\n\n"
        "Your advisory session has been confirmed.\n\n"
        f"  Date      : {booking.preferred_date}\n"
        f"  Time      : {booking.preferred_time} IST\n"
        f"  Topic     : {booking.issue_summary}\n"
        f"  Advisor   : {advisor_name}\n"
        f"  Booking ID: {booking.booking_id}\n\n"
        "Please keep your Booking ID for reference.\n\n"
        "Best regards,\n"
        "Groww Advisory Team\n"
    )


def _make_raw_message(*, to: str, sender: str, subject: str, body: str) -> str:
    msg = MIMEText(body, "plain")
    msg["to"] = to
    msg["from"] = sender
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return raw


# ── Public API ────────────────────────────────────────────────────────────────


def send_booking_confirmation(
    *,
    booking: BookingDetail,
    access_token: str | None,
) -> dict[str, Any]:
    """Send a booking confirmation email via the Gmail API.

    Args:
        booking:      The approved BookingDetail.
        access_token: A live OAuth2 access token with gmail.send scope.
                      Pass None to trigger a graceful skip.

    Returns:
        A result dict with keys:
          status     : "sent" | "skipped" | "failed"
          message_id : Gmail message ID (only when status="sent")
          reason     : human-readable explanation (only when status!="sent")
    """
    settings = get_settings()

    sender_email = settings.gmail_sender_email
    advisor_name = settings.google_authorized_email or "Groww Advisor"

    if not sender_email:
        logger.warning(
            "gmail_confirmation_skipped",
            extra={
                "booking_id": booking.booking_id,
                "reason": "GMAIL_SENDER_EMAIL not configured",
            },
        )
        return {"status": _SKIP, "reason": "GMAIL_SENDER_EMAIL not configured"}

    if not access_token:
        logger.warning(
            "gmail_confirmation_skipped",
            extra={
                "booking_id": booking.booking_id,
                "reason": "google_oauth_token not available",
            },
        )
        return {"status": _SKIP, "reason": "google_oauth_token not available"}

    subject = (
        f"Your advisory session has been confirmed — "
        f"{booking.preferred_date} at {booking.preferred_time}"
    )
    body = _build_email_body(booking, advisor_name)
    raw = _make_raw_message(
        to=booking.customer_email,
        sender=sender_email,
        subject=subject,
        body=body,
    )

    try:
        creds = Credentials(token=access_token)
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        result = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )
        message_id = result.get("id", "unknown")
        logger.info(
            "gmail_confirmation_sent",
            extra={"booking_id": booking.booking_id, "message_id": message_id},
        )
        return {"status": _SENT, "message_id": message_id}

    except HttpError as exc:
        logger.error(
            "gmail_confirmation_failed",
            extra={
                "booking_id": booking.booking_id,
                "error": str(exc),
                "http_status": exc.resp.status if exc.resp else None,
            },
        )
        return {"status": _FAILED, "reason": str(exc)}

    except Exception as exc:
        logger.error(
            "gmail_confirmation_failed",
            extra={"booking_id": booking.booking_id, "error": str(exc)},
        )
        return {"status": _FAILED, "reason": str(exc)}
