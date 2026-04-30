"""Google Calendar integration service — Phase 7.

Creates a 30-minute advisory session hold on the configured Google Calendar
when a booking is approved by the advisor.

Event spec (Phase 7):
  Title      : "Advisory Session — {customer_name}"
  Duration   : 30 minutes starting at preferred_date + preferred_time (IST)
  Calendar   : GOOGLE_CALENDAR_ID from Settings
  Description: issue_summary + Booking ID

Rules satisfied:
  I1  — external write goes through this dedicated integration module only.
  I2  — OAuth credentials stay server-side; access token is passed in.
  I5  — graceful degradation: returns a skip result when unconfigured.
  G5  — no secrets in code; all IDs come from Settings.
  G7  — known failure modes produce safe results; never raises to the caller.
  G9  — idempotency note: Calendar does not provide native idempotency keys;
         for Phase 7 we accept that a retry may create a duplicate event and
         document this as a known limitation (Phase 8 will add event dedup via
         the external_sync_logs table once it is migrated).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from app.core.config import get_settings
from app.schemas.booking import BookingDetail

logger = logging.getLogger(__name__)

_SKIP = "skipped"
_CREATED = "created"
_FAILED = "failed"

_IST = ZoneInfo("Asia/Kolkata")
_SESSION_DURATION_MINUTES = 30


def _parse_event_start(preferred_date: str, preferred_time: str) -> datetime:
    """Parse preferred_date (YYYY-MM-DD) and preferred_time (HH:MM) into an
    IST-aware datetime."""
    naive = datetime.strptime(f"{preferred_date}T{preferred_time}", "%Y-%m-%dT%H:%M")
    return naive.replace(tzinfo=_IST)


def _rfc3339(dt: datetime) -> str:
    """Format a datetime as RFC 3339 with timezone offset."""
    return dt.isoformat()


# ── Public API ────────────────────────────────────────────────────────────────


def create_calendar_hold(
    *,
    booking: BookingDetail,
    access_token: str | None,
) -> dict[str, Any]:
    """Create a Google Calendar event for the approved advisory session.

    Args:
        booking:      The approved BookingDetail.
        access_token: A live OAuth2 access token with calendar.events scope.
                      Pass None to trigger a graceful skip.

    Returns:
        A result dict with keys:
          status   : "created" | "skipped" | "failed"
          event_id : Google Calendar event ID (only when status="created")
          reason   : human-readable explanation (only when status!="created")
    """
    settings = get_settings()

    calendar_id = settings.google_calendar_id

    if not calendar_id:
        logger.warning(
            "calendar_hold_skipped",
            extra={
                "booking_id": booking.booking_id,
                "reason": "GOOGLE_CALENDAR_ID not configured",
            },
        )
        return {"status": _SKIP, "reason": "GOOGLE_CALENDAR_ID not configured"}

    if not access_token:
        logger.warning(
            "calendar_hold_skipped",
            extra={
                "booking_id": booking.booking_id,
                "reason": "google_oauth_token not available",
            },
        )
        return {"status": _SKIP, "reason": "google_oauth_token not available"}

    try:
        start_dt = _parse_event_start(booking.preferred_date, booking.preferred_time)
        end_dt = start_dt + timedelta(minutes=_SESSION_DURATION_MINUTES)
        tz_name = "Asia/Kolkata"

        event_body = {
            "summary": f"Advisory Session — {booking.customer_name}",
            "description": (
                f"{booking.issue_summary}\n\nBooking ID: {booking.booking_id}"
            ),
            "start": {
                "dateTime": _rfc3339(start_dt),
                "timeZone": tz_name,
            },
            "end": {
                "dateTime": _rfc3339(end_dt),
                "timeZone": tz_name,
            },
        }

        creds = Credentials(token=access_token)
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        created_event = (
            service.events()
            .insert(calendarId=calendar_id, body=event_body)
            .execute()
        )
        event_id = created_event.get("id", "unknown")
        logger.info(
            "calendar_hold_created",
            extra={"booking_id": booking.booking_id, "event_id": event_id},
        )
        return {"status": _CREATED, "event_id": event_id}

    except HttpError as exc:
        logger.error(
            "calendar_hold_failed",
            extra={
                "booking_id": booking.booking_id,
                "error": str(exc),
                "http_status": exc.resp.status if exc.resp else None,
            },
        )
        return {"status": _FAILED, "reason": str(exc)}

    except Exception as exc:
        logger.error(
            "calendar_hold_failed",
            extra={"booking_id": booking.booking_id, "error": str(exc)},
        )
        return {"status": _FAILED, "reason": str(exc)}
