"""Phase 5 automated evals: Booking and customer workflow state.

Checks (total weight = 100):
  1. openapi_booking_paths        (20) — all three booking routes in OpenAPI spec
  2. create_booking_happy_path    (30) — POST /booking/create → 201, booking_id, pending status
  3. get_booking_by_id            (20) — GET /booking/{id} returns the persisted booking
  4. cancel_booking_happy_path    (15) — POST /booking/cancel transitions to cancelled
  5. duplicate_submit_idempotent  (10) — same idempotency_key returns existing, not new
  6. invalid_cancel_errors_safe   ( 5) — non-existent + already-cancelled return safe responses

Threshold: >= 85% (EVAL11).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class Check:
    id: str
    weight: float
    fn: Callable[[], bool]


class Phase5EvalReport(BaseModel):
    version: str = Field(default="phase5-v1")
    total_weight: float
    earned_weight: float
    score: float
    checks: list[dict[str, object]]


def _client() -> TestClient:
    from app.main import app as fastapi_app

    return TestClient(fastapi_app, raise_server_exceptions=False)


def _future_date() -> str:
    """Return a date 7 days from today as YYYY-MM-DD."""
    return (date.today() + timedelta(days=7)).isoformat()


def _valid_create_body(idempotency_key: str | None = None) -> dict:
    body: dict = {
        "customer_name": "Priya Sharma",
        "customer_email": "priya@example.com",
        "issue_summary": "I have questions about my mutual fund SIP and fee structure.",
        "preferred_date": _future_date(),
        "preferred_time": "10:00",
    }
    if idempotency_key is not None:
        body["idempotency_key"] = idempotency_key
    return body


# ── Check 1: OpenAPI surface ─────────────────────────────────────────────────


def _openapi_booking_paths() -> bool:
    c = _client()
    spec = c.get("/openapi.json").json()
    paths = spec.get("paths") or {}
    need = [
        "/api/v1/booking/create",
        "/api/v1/booking/cancel",
        "/api/v1/booking/{booking_id}",
    ]
    return all(p in paths for p in need)


# ── Check 2: Create booking happy path ───────────────────────────────────────


def _create_booking_happy_path() -> bool:
    c = _client()
    r = c.post("/api/v1/booking/create", json=_valid_create_body())
    if r.status_code != 201:
        return False
    body = r.json()
    if body.get("success") is not True:
        return False
    data = body.get("data") or {}
    booking_id = data.get("booking_id", "")
    if not booking_id.startswith("BK-"):
        return False
    if data.get("status") != "pending_advisor_approval":
        return False
    # Timezone label must always be present (UI13, P5.2).
    if not data.get("display_timezone"):
        return False
    return True


# ── Check 3: Get booking by ID ───────────────────────────────────────────────


def _get_booking_by_id() -> bool:
    c = _client()
    # Create first.
    cr = c.post("/api/v1/booking/create", json=_valid_create_body())
    if cr.status_code != 201:
        return False
    booking_id = (cr.json().get("data") or {}).get("booking_id")
    if not booking_id:
        return False

    # Fetch by ID.
    gr = c.get(f"/api/v1/booking/{booking_id}")
    if gr.status_code != 200:
        return False
    gdata = (gr.json().get("data") or {})
    if gdata.get("booking_id") != booking_id:
        return False
    if gdata.get("status") != "pending_advisor_approval":
        return False
    return True


# ── Check 4: Cancel booking happy path ──────────────────────────────────────


def _cancel_booking_happy_path() -> bool:
    c = _client()
    # Create first.
    cr = c.post("/api/v1/booking/create", json=_valid_create_body())
    if cr.status_code != 201:
        return False
    booking_id = (cr.json().get("data") or {}).get("booking_id")
    if not booking_id:
        return False

    # Cancel it.
    xr = c.post("/api/v1/booking/cancel", json={"booking_id": booking_id, "reason": "Changed mind"})
    if xr.status_code != 200:
        return False
    xbody = xr.json()
    if xbody.get("success") is not True:
        return False
    xdata = xbody.get("data") or {}
    if xdata.get("status") != "cancelled":
        return False
    if xdata.get("cancellation_reason") != "Changed mind":
        return False
    return True


# ── Check 5: Duplicate submit idempotency ────────────────────────────────────


def _duplicate_submit_idempotent() -> bool:
    c = _client()
    ikey = "eval-idem-key-001"
    body = _valid_create_body(idempotency_key=ikey)

    r1 = c.post("/api/v1/booking/create", json=body)
    if r1.status_code != 201:
        return False
    bid1 = (r1.json().get("data") or {}).get("booking_id")

    # Second identical submit — must return 409 with the same booking_id.
    r2 = c.post("/api/v1/booking/create", json=body)
    if r2.status_code != 409:
        return False
    r2body = r2.json()
    # Data must carry the existing booking (so the client can reconcile).
    bid2 = (r2body.get("data") or {}).get("booking_id")
    return bid1 == bid2


# ── Check 6: Invalid cancel returns safe errors ──────────────────────────────


def _invalid_cancel_errors_safe() -> bool:
    c = _client()

    # 6a: Non-existent booking ID → 404 with safe message.
    r_ne = c.post("/api/v1/booking/cancel", json={"booking_id": "BK-NONEXIST-XXXX"})
    if r_ne.status_code != 404:
        return False
    detail_ne = r_ne.json().get("detail") or {}
    if detail_ne.get("code") != "booking_not_found":
        return False

    # 6b: Cancel an already-cancelled booking → 200 with idempotent message.
    cr = c.post("/api/v1/booking/create", json=_valid_create_body())
    if cr.status_code != 201:
        return False
    booking_id = (cr.json().get("data") or {}).get("booking_id")

    c.post("/api/v1/booking/cancel", json={"booking_id": booking_id})  # first cancel
    r_dup = c.post("/api/v1/booking/cancel", json={"booking_id": booking_id})  # second cancel
    if r_dup.status_code != 200:
        return False
    dup_body = r_dup.json()
    dup_errors = dup_body.get("errors") or []
    if not any(e.get("code") == "booking_already_cancelled" for e in dup_errors):
        return False

    return True


# ── Harness ──────────────────────────────────────────────────────────────────


def run_phase5_evals() -> Phase5EvalReport:
    """Run all Phase 5 checks in a stable offline context."""
    with patch(
        "app.integrations.supabase.client.check_supabase_connectivity",
        new=AsyncMock(return_value=(True, "ok")),
    ):
        checks: list[Check] = [
            Check("openapi_booking_paths", 20.0, _openapi_booking_paths),
            Check("create_booking_happy_path", 30.0, _create_booking_happy_path),
            Check("get_booking_by_id", 20.0, _get_booking_by_id),
            Check("cancel_booking_happy_path", 15.0, _cancel_booking_happy_path),
            Check("duplicate_submit_idempotent", 10.0, _duplicate_submit_idempotent),
            Check("invalid_cancel_errors_safe", 5.0, _invalid_cancel_errors_safe),
        ]

        earned = 0.0
        total = 0.0
        rows: list[dict[str, object]] = []

        for chk in checks:
            total += chk.weight
            ok = False
            try:
                ok = bool(chk.fn())
            except Exception as exc:
                ok = False
                rows.append({"id": chk.id, "weight": chk.weight, "passed": ok, "error": str(exc)})
                continue
            if ok:
                earned += chk.weight
            rows.append({"id": chk.id, "weight": chk.weight, "passed": ok})

        score = round((earned / total) * 100.0, 2) if total else 0.0
        return Phase5EvalReport(
            total_weight=total,
            earned_weight=earned,
            score=score,
            checks=rows,
        )
