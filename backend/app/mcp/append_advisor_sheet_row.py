"""MCP action: append_advisor_sheet_row — Phase 7.

Thin governed action wrapper over sheets_service.append_advisor_sheet_row.

Per Architecture.md §MCP architecture, MCP actions should be:
  - small
  - explicit
  - idempotent where possible
  - easy to log and debug

All business logic lives in services/sheets_service.py.
This module exists to keep the MCP boundary explicit (Architecture §5, I9).
Google Sheets is never the source of truth — it is a downstream export surface
only (Architecture.md §Architectural principles 3).
"""

from __future__ import annotations

from typing import Any

from app.schemas.booking import BookingDetail
from app.services.sheets_service import append_advisor_sheet_row as _append


async def append_advisor_sheet_row(
    *,
    booking: BookingDetail,
    access_token: str | None,
) -> dict[str, Any]:
    """MCP action: append an advisor export row to the Google Sheet.

    Delegates to sheets_service.append_advisor_sheet_row.
    Returns the service result dict directly.
    """
    return _append(booking=booking, access_token=access_token)
