"""Google Sheets integration service — Phase 7.

Appends a single advisor export row to the configured Google Sheet when a
booking is approved.  Sheets is a downstream operational surface only; it is
never the source of truth (Architecture.md §Architectural principles 3).

Row spec (Phase 7):
  Columns: booking_id | customer_name | customer_email | preferred_date |
           preferred_time | status | approved_at (UTC ISO) | issue_summary

Rules satisfied:
  I1  — external write goes through this dedicated integration module only.
  I2  — OAuth credentials stay server-side; access token is passed in.
  I5  — graceful degradation: returns a skip result when unconfigured.
  G5  — no secrets in code; all IDs come from Settings.
  G7  — known failure modes produce safe results; never raises to the caller.
  Architecture §3 — Sheets is never used as source of truth.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from app.core.config import get_settings
from app.schemas.booking import BookingDetail

logger = logging.getLogger(__name__)

_SKIP = "skipped"
_APPENDED = "appended"
_FAILED = "failed"

# Column order for the advisor export sheet.
_COLUMNS = [
    "booking_id",
    "customer_name",
    "customer_email",
    "preferred_date",
    "preferred_time",
    "status",
    "approved_at",
    "issue_summary",
]


def _build_row(booking: BookingDetail) -> list[str]:
    approved_at = datetime.now(timezone.utc).isoformat()
    return [
        booking.booking_id,
        booking.customer_name,
        booking.customer_email,
        booking.preferred_date,
        booking.preferred_time,
        booking.status.value,
        approved_at,
        booking.issue_summary,
    ]


# ── Public API ────────────────────────────────────────────────────────────────


def append_advisor_sheet_row(
    *,
    booking: BookingDetail,
    access_token: str | None,
) -> dict[str, Any]:
    """Append an advisor export row to the configured Google Sheet.

    Args:
        booking:      The approved BookingDetail.
        access_token: A live OAuth2 access token with spreadsheets scope.
                      Pass None to trigger a graceful skip.

    Returns:
        A result dict with keys:
          status : "appended" | "skipped" | "failed"
          row    : the list of cell values written (only when status="appended")
          reason : human-readable explanation (only when status!="appended")
    """
    settings = get_settings()

    spreadsheet_id = settings.google_sheets_spreadsheet_id
    worksheet_name = settings.google_sheets_worksheet_name or "Sheet1"

    if not spreadsheet_id:
        logger.warning(
            "sheets_row_skipped",
            extra={
                "booking_id": booking.booking_id,
                "reason": "GOOGLE_SHEETS_SPREADSHEET_ID not configured",
            },
        )
        return {
            "status": _SKIP,
            "reason": "GOOGLE_SHEETS_SPREADSHEET_ID not configured",
        }

    if not access_token:
        logger.warning(
            "sheets_row_skipped",
            extra={
                "booking_id": booking.booking_id,
                "reason": "google_oauth_token not available",
            },
        )
        return {"status": _SKIP, "reason": "google_oauth_token not available"}

    row = _build_row(booking)

    try:
        creds = Credentials(token=access_token)
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        range_notation = f"{worksheet_name}!A:H"
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_notation,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

        logger.info(
            "sheets_row_appended",
            extra={"booking_id": booking.booking_id, "row": row},
        )
        return {"status": _APPENDED, "row": row}

    except HttpError as exc:
        logger.error(
            "sheets_row_failed",
            extra={
                "booking_id": booking.booking_id,
                "error": str(exc),
                "http_status": exc.resp.status if exc.resp else None,
            },
        )
        return {"status": _FAILED, "reason": str(exc)}

    except Exception as exc:
        logger.error(
            "sheets_row_failed",
            extra={"booking_id": booking.booking_id, "error": str(exc)},
        )
        return {"status": _FAILED, "reason": str(exc)}
