"""Google Sheets integration service — Phase 7.

Writes a single advisor export row to the configured Google Sheet when a
booking is approved.  Sheets is a downstream operational surface only; it is
never the source of truth (Architecture.md §Architectural principles 3).

Sheet column contract (6 columns, matching the headers defined in the sheet):
  A: Booking ID
  B: Status                    → "Approved"  (chip/dropdown value)
  C: Customer Concern          → customer_email  — the sheet column is typed as a
                                 "People chip"; writing a valid email address causes
                                 Sheets to resolve it automatically into a contact chip.
  D: Advisor Appointment Category → keyword-derived category string
                                    (e.g. "Mutual Funds & SIP", "Tax Planning")
  E: Date of Calendar Hold     → "DD Mon YYYY, HH:MM IST"
                                 (USER_ENTERED so Sheets treats it as a date cell)
  F: AI Chat Summary           → issue_summary (Phase 7 proxy; Phase 8 adds LLM summary)

Row insertion strategy:
  Scan column A from row 2 downwards and write to the FIRST empty cell found.
  This keeps data in ascending order directly below the header row, avoids
  phantom rows, and does not depend on the Sheets API's own "after last row"
  heuristic (which placed rows at 1016 on a sheet full of empty-but-formatted
  rows).  The grid is auto-expanded by 200 rows if the first empty row would
  exceed the current grid size.

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
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from app.core.config import get_settings
from app.schemas.booking import BookingDetail

logger = logging.getLogger(__name__)

_SKIP     = "skipped"
_APPENDED = "appended"
_FAILED   = "failed"

_IST = ZoneInfo("Asia/Kolkata")

_MONTHS = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# ── Category classifier ───────────────────────────────────────────────────────

# Keyword → category label.  The first match wins; order from most-specific
# to most-general.  Written as plain text that works whether or not the sheet
# column has chip-style dropdown validation.
_CATEGORY_MAP: list[tuple[list[str], str]] = [
    (["sip", "systematic investment", "expense ratio"], "Mutual Funds & SIP"),
    (["mutual fund", "elss", "nfo", "nav"],             "Mutual Funds & SIP"),
    (["tax", "itr", "80c", "capital gain"],              "Tax Planning"),
    (["retirement", "pension", "nps"],                   "Retirement Planning"),
    (["insurance", "term plan", "health cover"],         "Insurance & Protection"),
    (["portfolio", "rebalance", "asset allocation"],     "Portfolio Review"),
    (["goal", "house", "education", "wedding"],          "Financial Goals"),
    (["stock", "equity", "share", "ipo"],                "Equity & Stocks"),
    (["fd", "fixed deposit", "debt", "bond"],            "Debt & Fixed Income"),
]
_DEFAULT_CATEGORY = "General Financial Advisory"


def _derive_category(issue_summary: str) -> str:
    """Return the best-matching category label for the given issue text."""
    lower = issue_summary.lower()
    for keywords, label in _CATEGORY_MAP:
        if any(kw in lower for kw in keywords):
            return label
    return _DEFAULT_CATEGORY


# ── Formatting helpers ────────────────────────────────────────────────────────


def _format_date_of_hold(preferred_date: str, preferred_time: str) -> str:
    """Return a human-readable date+time string that Sheets parses as a date cell.

    Format: "01 Jun 2026, 14:00 IST"
    Using USER_ENTERED allows Sheets to recognise this as a date/time value
    while keeping the IST timezone label visible.
    """
    try:
        dt = datetime.strptime(f"{preferred_date} {preferred_time}", "%Y-%m-%d %H:%M")
        return f"{dt.day:02d} {_MONTHS[dt.month]} {dt.year}, {dt.hour:02d}:{dt.minute:02d} IST"
    except ValueError:
        return f"{preferred_date} {preferred_time} IST"


def _build_row(booking: BookingDetail) -> list[str]:
    """Build the 6-cell row matching the sheet's defined column headers A–F.

    Column C is a People-chip column: writing a valid email address causes
    Sheets to auto-resolve it into a contact chip on save/refresh.
    Column D derives an appointment category from the booking's issue_summary.
    """
    return [
        booking.booking_id,                                          # A: Booking ID
        "Approved",                                                  # B: Status (chip)
        booking.customer_email,                                      # C: Customer Concern (people chip)
        _derive_category(booking.issue_summary),                     # D: Advisor Appointment Category
        _format_date_of_hold(
            booking.preferred_date, booking.preferred_time          # E: Date of Calendar Hold
        ),
        booking.issue_summary,                                       # F: AI Chat Summary
    ]


# ── Sheet metadata & grid management ─────────────────────────────────────────


def _get_sheet_meta(
    service: Any, spreadsheet_id: str, worksheet_name: str
) -> tuple[int, int]:
    """Return (sheetId, rowCount) for the named worksheet."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in meta.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == worksheet_name:
            grid = props.get("gridProperties", {})
            return props["sheetId"], grid.get("rowCount", 1000)
    raise ValueError(f"Worksheet '{worksheet_name}' not found in spreadsheet.")


def _expand_sheet_rows(
    service: Any, spreadsheet_id: str, sheet_id: int, rows_to_add: int = 200
) -> None:
    """Append rows to the grid so a write does not exceed grid limits."""
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{
            "appendDimension": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "length": rows_to_add,
            }
        }]},
    ).execute()


def _find_first_empty_row(
    service: Any,
    spreadsheet_id: str,
    worksheet_name: str,
) -> tuple[int, int]:
    """Return (first_empty_row, sheet_id) scanning col A from row 2 downward.

    'First empty row' means the lowest-numbered row ≥ 2 whose column A cell
    has no value.  If every row in the current grid is occupied the grid is
    expanded by 200 rows and the next row number is returned.
    """
    sheet_id, grid_rows = _get_sheet_meta(service, spreadsheet_id, worksheet_name)

    col_a = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{worksheet_name}!A:A",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute().get("values", [])

    # idx is 0-based; row = idx + 1.  Start at idx=1 (row 2) to skip the header.
    for idx in range(1, len(col_a)):
        cell = col_a[idx]
        if not cell or not str(cell[0]).strip():
            return idx + 1, sheet_id

    # All rows in col A have content (or col A is empty below row 1).
    next_row = len(col_a) + 1
    if next_row > grid_rows:
        _expand_sheet_rows(service, spreadsheet_id, sheet_id, rows_to_add=200)
    return next_row, sheet_id


# ── Public API ────────────────────────────────────────────────────────────────


def append_advisor_sheet_row(
    *,
    booking: BookingDetail,
    access_token: str | None,
) -> dict[str, Any]:
    """Write an advisor export row into the first empty row below the header.

    Uses USER_ENTERED so that Sheets parses the date/time cell correctly and
    resolves the email address in col C into a People chip.

    Returns:
        status      : "appended" | "skipped" | "failed"
        row         : cell values written  (when status="appended")
        written_to  : 1-indexed row number (when status="appended")
        reason      : explanation          (when status!="appended")
    """
    settings = get_settings()
    spreadsheet_id = settings.google_sheets_spreadsheet_id
    worksheet_name = settings.google_sheets_worksheet_name or "Sheet1"

    if not spreadsheet_id:
        logger.warning(
            "sheets_row_skipped",
            extra={"booking_id": booking.booking_id,
                   "reason": "GOOGLE_SHEETS_SPREADSHEET_ID not configured"},
        )
        return {"status": _SKIP, "reason": "GOOGLE_SHEETS_SPREADSHEET_ID not configured"}

    if not access_token:
        logger.warning(
            "sheets_row_skipped",
            extra={"booking_id": booking.booking_id,
                   "reason": "google_oauth_token not available"},
        )
        return {"status": _SKIP, "reason": "google_oauth_token not available"}

    row = _build_row(booking)

    try:
        creds = Credentials(token=access_token)
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)

        target_row, _sheet_id = _find_first_empty_row(service, spreadsheet_id, worksheet_name)
        write_range = f"{worksheet_name}!A{target_row}"

        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=write_range,
            valueInputOption="USER_ENTERED",
            body={"values": [row]},
        ).execute()

        logger.info(
            "sheets_row_appended",
            extra={
                "booking_id": booking.booking_id,
                "row": row,
                "written_to_row": target_row,
            },
        )
        return {"status": _APPENDED, "row": row, "written_to": target_row}

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
