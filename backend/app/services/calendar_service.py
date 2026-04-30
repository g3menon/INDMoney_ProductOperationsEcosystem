"""Google Calendar integration service — Phase 7.

Creates a 30-minute advisory session hold on the configured Google Calendar
when a booking is approved by the advisor.

Event spec (Phase 7):
  Title      : "Advisory Session — {customer_name}"
  Duration   : 30 minutes starting at preferred_date + preferred_time (IST)
  Calendar   : GOOGLE_CALENDAR_ID from Settings
  Description: issue_summary + Booking ID

Guards (Phase 7):
  1. Past-date guard  — booking slot must be in the future; stale/past slots
     are skipped with a warning rather than creating a nonsense calendar event.
  2. FreeBusy conflict check — query the Calendar API for existing events in
     the proposed window.  If a conflict is found the event is NOT created and
     a structured warning is returned so the advisor can reschedule.

Rules satisfied:
  I1  — external write goes through this dedicated integration module only.
  I2  — OAuth credentials stay server-side; access token is passed in.
  I5  — graceful degradation: returns a skip/conflict result when appropriate.
  G5  — no secrets in code; all IDs come from Settings.
  G7  — known failure modes produce safe results; never raises to the caller.
  G9  — conflict guard prevents duplicate event creation on retries when the
         slot is already taken.
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
_CONFLICT = "conflict"

_IST = ZoneInfo("Asia/Kolkata")
_SESSION_DURATION_MINUTES = 30


def _parse_event_start(preferred_date: str, preferred_time: str) -> datetime:
    """Parse preferred_date (YYYY-MM-DD) and preferred_time (HH:MM) into IST-aware datetime."""
    naive = datetime.strptime(f"{preferred_date}T{preferred_time}", "%Y-%m-%dT%H:%M")
    return naive.replace(tzinfo=_IST)


def _rfc3339(dt: datetime) -> str:
    return dt.isoformat()


def _check_conflicts(
    service: Any,
    calendar_id: str,
    start_dt: datetime,
    end_dt: datetime,
) -> list[dict]:
    """Return list of non-cancelled events that overlap the proposed window.

    Uses events.list (requires calendar.events scope) instead of freeBusy
    (which would require calendar.readonly scope not included in Phase 7 token).
    """
    result = service.events().list(
        calendarId=calendar_id,
        timeMin=_rfc3339(start_dt),
        timeMax=_rfc3339(end_dt),
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    events = result.get("items", [])
    # Exclude cancelled events from conflict consideration.
    return [
        {"id": e.get("id"), "summary": e.get("summary"), "start": e.get("start")}
        for e in events
        if e.get("status") != "cancelled"
    ]


# ── Public API ────────────────────────────────────────────────────────────────


def create_calendar_hold(
    *,
    booking: BookingDetail,
    access_token: str | None,
) -> dict[str, Any]:
    """Create a Google Calendar event for the approved advisory session.

    Returns early with a structured result (never raises) in these cases:
      - GOOGLE_CALENDAR_ID not set           → status="skipped"
      - access_token is None                 → status="skipped"
      - preferred slot is in the past        → status="skipped", reason="past_slot"
      - an existing event occupies the slot  → status="conflict", busy=[...]
      - any Google API error                 → status="failed"

    Args:
        booking:      The approved BookingDetail.
        access_token: A live OAuth2 access token with calendar.events scope.

    Returns:
        A result dict with keys:
          status   : "created" | "skipped" | "conflict" | "failed"
          event_id : Google Calendar event ID (only when status="created")
          busy     : list of conflicting periods (only when status="conflict")
          reason   : human-readable explanation (when status != "created")
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
        now_ist = datetime.now(tz=_IST)

        # ── Guard 1: reject past slots ────────────────────────────────────────
        if start_dt <= now_ist:
            logger.warning(
                "calendar_hold_skipped",
                extra={
                    "booking_id": booking.booking_id,
                    "reason": "past_slot",
                    "slot": _rfc3339(start_dt),
                    "now": _rfc3339(now_ist),
                },
            )
            return {
                "status": _SKIP,
                "reason": (
                    f"Slot {booking.preferred_date} {booking.preferred_time} IST "
                    f"is in the past — no calendar event created."
                ),
            }

        creds = Credentials(token=access_token)
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        # ── Guard 2: check for existing events in the slot ───────────────────
        conflicts = _check_conflicts(service, calendar_id, start_dt, end_dt)
        if conflicts:
            logger.warning(
                "calendar_hold_conflict",
                extra={
                    "booking_id": booking.booking_id,
                    "slot": _rfc3339(start_dt),
                    "conflicting_events": conflicts,
                },
            )
            return {
                "status": _CONFLICT,
                "reason": (
                    f"Slot {booking.preferred_date} {booking.preferred_time} IST "
                    f"conflicts with an existing calendar event. Advisor should reschedule."
                ),
                "conflicting_events": conflicts,
            }

        # ── Create the event ──────────────────────────────────────────────────
        tz_name = "Asia/Kolkata"
        event_body = {
            "summary": f"Advisory Session \u2014 {booking.customer_name}",
            "description": (
                f"{booking.issue_summary}\n\nBooking ID: {booking.booking_id}"
            ),
            "start": {"dateTime": _rfc3339(start_dt), "timeZone": tz_name},
            "end": {"dateTime": _rfc3339(end_dt), "timeZone": tz_name},
        }

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
