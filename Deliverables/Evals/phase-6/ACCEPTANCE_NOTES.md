# Phase 6 — Advisor HITL Approval: Acceptance Notes

Manual test guide for the **advisor approval and rejection workflow**.
Run these steps after starting the backend locally (`uvicorn app.main:app --reload`).

---

## Prerequisites

- Backend running on `http://localhost:8000`
- Phase 5 bookings endpoint is live (`POST /api/v1/booking/create` works)
- `BOOKING_STORAGE_MODE` is unset (uses in-memory) or set to `supabase` (real DB)
- All Phase 6 migrations applied if using Supabase: `infra/supabase/phase6_schema.sql`

---

## Step 1 — Seed a pending booking

```bash
curl -s -X POST http://localhost:8000/api/v1/booking/create \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "Priya Sharma",
    "customer_email": "priya@example.com",
    "issue_summary": "Need advice on switching from index funds to active large-cap funds",
    "preferred_date": "2026-05-15",
    "preferred_time": "10:00",
    "idempotency_key": "test-phase6-001"
  }' | python -m json.tool
```

**Expected:** `HTTP 201`, `status: "pending_advisor_approval"`, response contains a
`booking_id` like `BK-20260430-XXXX`.  Copy this `booking_id` for the steps below.

---

## Step 2 — GET /advisor/pending (happy path)

```bash
curl -s http://localhost:8000/api/v1/advisor/pending | python -m json.tool
```

**Expected:**
```json
{
  "success": true,
  "message": "pending_approvals",
  "data": {
    "items": [{ "booking_id": "BK-...", "status": "pending_advisor_approval", ... }],
    "count": 1
  },
  "errors": []
}
```

---

## Step 3 — POST /advisor/approve/{booking_id} (approve happy path)

Replace `BK-XXXX` with the actual booking_id from Step 1.

```bash
curl -s -X POST http://localhost:8000/api/v1/advisor/approve/BK-XXXX \
  -H "Content-Type: application/json" \
  -d '{"reason": "Customer profile matches advisory criteria"}' | python -m json.tool
```

**Expected:**
```json
{
  "success": true,
  "message": "booking_approved",
  "data": {
    "booking_id": "BK-XXXX",
    "previous_status": "pending_advisor_approval",
    "new_status": "approved",
    "idempotent": false,
    "booking": { "status": "approved", ... }
  },
  "errors": []
}
```

---

## Step 4 — GET /advisor/upcoming (confirms approved booking appears)

```bash
curl -s http://localhost:8000/api/v1/advisor/upcoming | python -m json.tool
```

**Expected:** `count: 1`, item shows `status: "approved"`.

Also confirm pending list is now empty:

```bash
curl -s http://localhost:8000/api/v1/advisor/pending | python -m json.tool
# Expected: count: 0
```

---

## Step 5 — Duplicate approval (idempotency test)

Call approve a second time on the same booking:

```bash
curl -s -X POST http://localhost:8000/api/v1/advisor/approve/BK-XXXX \
  -H "Content-Type: application/json" \
  -d '{"reason": "Re-clicked by accident"}' | python -m json.tool
```

**Expected:**
```json
{
  "success": true,
  "message": "booking_approved_idempotent",
  "data": { "idempotent": true, "new_status": "approved", ... },
  "errors": [{ "code": "approval_already_approved", ... }]
}
```
HTTP status is **200**; no second `booking_events` row is written.

---

## Step 6 — Reject path (seed a new booking first)

```bash
# Seed second booking
curl -s -X POST http://localhost:8000/api/v1/booking/create \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "Rahul Verma",
    "customer_email": "rahul@example.com",
    "issue_summary": "Query about ELSS tax saving funds",
    "preferred_date": "2026-05-20",
    "preferred_time": "14:00",
    "idempotency_key": "test-phase6-002"
  }' | python -m json.tool
# Copy the new booking_id → BK-YYYY

curl -s -X POST http://localhost:8000/api/v1/advisor/reject/BK-YYYY \
  -H "Content-Type: application/json" \
  -d '{"reason": "Requires specialist not currently available"}' | python -m json.tool
```

**Expected:** `new_status: "rejected"`, `idempotent: false`.

---

## Step 7 — Reject an already-rejected booking (idempotency)

```bash
curl -s -X POST http://localhost:8000/api/v1/advisor/reject/BK-YYYY \
  -H "Content-Type: application/json" \
  -d '{"reason": "Second click"}' | python -m json.tool
```

**Expected:** HTTP 200, `idempotent: true`, `message: "booking_rejected_idempotent"`.

---

## Step 8 — Cross-state error: approve a rejected booking

```bash
curl -s -X POST http://localhost:8000/api/v1/advisor/approve/BK-YYYY \
  -H "Content-Type: application/json" \
  -d '{"reason": "Changed mind"}' | python -m json.tool
```

**Expected:** HTTP **409 Conflict**, `code: "booking_already_rejected"`.

---

## Step 9 — Cross-state error: reject an approved booking

```bash
curl -s -X POST http://localhost:8000/api/v1/advisor/reject/BK-XXXX \
  -H "Content-Type: application/json" \
  -d '{"reason": "Changed mind"}' | python -m json.tool
```

**Expected:** HTTP **409 Conflict**, `code: "booking_already_approved"`.

---

## Step 10 — /approval/{id}/approve path (architecture-spec alt route)

Both `/advisor/approve/{id}` and `/approval/{id}/approve` point to the same service.
Verify the alternate path also works:

```bash
# Seed another booking
curl -s -X POST http://localhost:8000/api/v1/booking/create \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "Ananya Iyer",
    "customer_email": "ananya@example.com",
    "issue_summary": "Rebalancing portfolio query",
    "preferred_date": "2026-05-22",
    "preferred_time": "11:30",
    "idempotency_key": "test-phase6-003"
  }' | python -m json.tool
# Copy booking_id → BK-ZZZZ

curl -s -X POST http://localhost:8000/api/v1/approval/BK-ZZZZ/approve \
  -H "Content-Type: application/json" \
  -d '{}' | python -m json.tool
```

**Expected:** HTTP 200, `new_status: "approved"`.

---

## Step 11 — 404 for unknown booking

```bash
curl -s -X POST http://localhost:8000/api/v1/advisor/approve/BK-DOESNOTEXIST \
  -H "Content-Type: application/json" \
  -d '{}' | python -m json.tool
```

**Expected:** HTTP **404**, `code: "booking_not_found"`.

---

## Step 12 — OpenAPI surface check

```bash
curl -s http://localhost:8000/openapi.json | python -m json.tool | grep '"path"'
# Should include:
#  /api/v1/advisor/pending
#  /api/v1/advisor/upcoming
#  /api/v1/advisor/approve/{booking_id}
#  /api/v1/advisor/reject/{booking_id}
#  /api/v1/approval/{approval_id}/approve
#  /api/v1/approval/{approval_id}/reject
```

---

## Definition of Done checklist (Rules.md Phase 6)

- [ ] `GET /advisor/pending` returns bookings in `pending_advisor_approval` state
- [ ] `GET /advisor/upcoming` returns bookings in `approved` / `confirmation_sent` state
- [ ] `POST /advisor/approve/{id}` transitions to `approved`, writes `booking_events` audit row
- [ ] `POST /advisor/reject/{id}` transitions to `rejected`, writes `booking_events` audit row
- [ ] Duplicate approve → HTTP 200, `idempotent: true`, no second event row
- [ ] Duplicate reject  → HTTP 200, `idempotent: true`, no second event row
- [ ] Approve rejected booking → HTTP 409
- [ ] Reject approved booking  → HTTP 409
- [ ] Unknown booking → HTTP 404
- [ ] Phase 7 TODO stubs visible at correct insertion points in `approval_workflow_service.py`

---

## Phase 7 stubs (do not implement yet)

The following side effects are **not triggered in Phase 6**. TODOs are in
`backend/app/services/approval_workflow_service.py`:

- `mcp.send_booking_confirmation(booking, actor)` — customer confirmation email via Gmail
- `mcp.create_calendar_hold(booking, actor)` — calendar event via Google Calendar
- `mcp.append_advisor_sheet_row(booking)` — optional Sheets append

These will be wired in Phase 7 without any changes to the approval state machine.
