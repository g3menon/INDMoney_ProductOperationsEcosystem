"""MCP action: create_calendar_hold — Phase 7.

Thin governed action wrapper over calendar_service.create_calendar_hold.

Per Architecture.md §MCP architecture, MCP actions should be:
  - small
  - explicit
  - idempotent where possible
  - easy to log and debug

All business logic lives in services/calendar_service.py.
This module exists to keep the MCP boundary explicit (Architecture §5, I9).
"""

from __future__ import annotations

from typing import Any

from app.schemas.booking import BookingDetail
from app.services.calendar_service import create_calendar_hold as _create


async def create_calendar_hold(
    *,
    booking: BookingDetail,
    access_token: str | None,
) -> dict[str, Any]:
    """MCP action: create a Google Calendar event for the advisory session.

    Delegates to calendar_service.create_calendar_hold.
    Returns the service result dict directly.
    """
    return _create(booking=booking, access_token=access_token)
