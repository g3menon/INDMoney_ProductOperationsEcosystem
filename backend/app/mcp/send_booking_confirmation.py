"""MCP action: send_booking_confirmation — Phase 7.

Thin governed action wrapper over gmail_service.send_booking_confirmation.

Per Architecture.md §MCP architecture, MCP actions should be:
  - small
  - explicit
  - idempotent where possible
  - easy to log and debug

All business logic lives in services/gmail_service.py.
This module exists to keep the MCP boundary explicit (Architecture §5, I9).
"""

from __future__ import annotations

from typing import Any

from app.schemas.booking import BookingDetail
from app.services.gmail_service import send_booking_confirmation as _send


async def send_booking_confirmation(
    *,
    booking: BookingDetail,
    access_token: str | None,
) -> dict[str, Any]:
    """MCP action: send a booking confirmation email via Gmail.

    Delegates to gmail_service.send_booking_confirmation.
    Returns the service result dict directly.
    """
    return _send(booking=booking, access_token=access_token)
