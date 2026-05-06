"""MCP action: send_weekly_pulse_email — Phase 7.

Thin governed action for sending the latest weekly pulse to a single subscriber.
This is used by the scheduler service and is intentionally small and explicit.
"""

from __future__ import annotations

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from app.core.config import get_settings
from app.mcp.pulse_email_template import build_pulse_email_parts
from app.repositories.log_repository import log_email_action, log_pulse_send
from app.schemas.pulse import WeeklyPulse
from app.repositories.token_repository import get_google_oauth_token

logger = logging.getLogger(__name__)


def _make_raw_message(*, to: str, sender: str, subject: str, plain: str, html: str) -> str:
    msg = MIMEMultipart("alternative")
    msg["to"] = to
    msg["from"] = sender
    msg["subject"] = subject
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


async def send_weekly_pulse_email(
    *,
    pulse: WeeklyPulse | None,
    to_email: str,
    correlation_id: str | None,
) -> dict[str, Any]:
    """Send the weekly pulse email to a single subscriber.

    Returns a small status dict; callers should treat failures as non-fatal.
    """
    settings = get_settings()
    sender_email = settings.gmail_sender_email

    subject, plain, html = build_pulse_email_parts(pulse)
    pulse_id = pulse.pulse_id if pulse else None

    if not sender_email:
        await log_pulse_send(settings=settings, pulse_id=pulse_id, email=to_email, status="skipped", error="sender_missing")
        return {"status": "skipped", "reason": "GMAIL_SENDER_EMAIL not configured"}

    access_token = await get_google_oauth_token()
    if not access_token:
        await log_pulse_send(settings=settings, pulse_id=pulse_id, email=to_email, status="skipped", error="token_missing")
        return {"status": "skipped", "reason": "google_oauth_token not available"}

    raw = _make_raw_message(to=to_email, sender=sender_email, subject=subject, plain=plain, html=html)

    # Idempotency key: pulse_id + email (best-effort; DB enforces uniqueness if configured)
    idem = f"weekly_pulse:{pulse_id or 'none'}:{to_email.lower()}"

    try:
        creds = Credentials(token=access_token)
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        message_id = result.get("id", "unknown")

        await log_pulse_send(
            settings=settings,
            pulse_id=pulse_id,
            email=to_email,
            status="sent",
            provider_message_id=message_id,
        )
        await log_email_action(
            settings=settings,
            correlation_id=correlation_id,
            idempotency_key=idem,
            action_type="weekly_pulse",
            booking_id=None,
            pulse_id=pulse_id,
            to_email=to_email,
            from_email=sender_email,
            subject=subject,
            status="sent",
            provider_message_id=message_id,
            error=None,
        )

        logger.info(
            "weekly_pulse_email_sent",
            extra={"pulse_id": pulse_id, "email": to_email, "message_id": message_id},
        )
        return {"status": "sent", "message_id": message_id}

    except HttpError as exc:
        err = str(exc)
        await log_pulse_send(settings=settings, pulse_id=pulse_id, email=to_email, status="failed", error=err)
        await log_email_action(
            settings=settings,
            correlation_id=correlation_id,
            idempotency_key=idem,
            action_type="weekly_pulse",
            booking_id=None,
            pulse_id=pulse_id,
            to_email=to_email,
            from_email=sender_email,
            subject=subject,
            status="failed",
            provider_message_id=None,
            error=err,
        )
        logger.error("weekly_pulse_email_failed", extra={"pulse_id": pulse_id, "email": to_email, "error": err})
        return {"status": "failed", "reason": err}

    except Exception as exc:
        err = str(exc)
        await log_pulse_send(settings=settings, pulse_id=pulse_id, email=to_email, status="failed", error=err)
        await log_email_action(
            settings=settings,
            correlation_id=correlation_id,
            idempotency_key=idem,
            action_type="weekly_pulse",
            booking_id=None,
            pulse_id=pulse_id,
            to_email=to_email,
            from_email=sender_email,
            subject=subject,
            status="failed",
            provider_message_id=None,
            error=err,
        )
        logger.error("weekly_pulse_email_failed", extra={"pulse_id": pulse_id, "email": to_email, "error": err})
        return {"status": "failed", "reason": err}
