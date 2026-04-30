Phase 5 Acceptance Notes — Booking and customer workflow state

Gate result: PASS
Automated score: 100.0% (threshold 85%)
Date: 2026-04-30
Artifact: eval_20260430T091041Z_phase5-v1.json

---

Automated checks (all passed)

  openapi_booking_paths       PASS  20/20
  create_booking_happy_path   PASS  30/30
  get_booking_by_id           PASS  20/20
  cancel_booking_happy_path   PASS  15/15
  duplicate_submit_idempotent PASS  10/10
  invalid_cancel_errors_safe  PASS   5/5

  Total: 100/100

---

Phase 5 Definition of Done (Docs/Rules.md P5.x)

P5.1 Booking logic lives in backend services, not UI
     ✓ booking_workflow_service.py owns all state machine logic

P5.2 Timezone clarity is mandatory
     ✓ Every BookingDetail response carries display_timezone (e.g. "Asia/Kolkata (IST)")
     ✓ Timestamps stored as UTC; display label carries the IST annotation (UI13)

P5.3 Booking identifiers must be collision-safe
     ✓ Format: BK-YYYYMMDD-XXXX (4 uppercase hex chars from UUID4)

P5.4 State transitions must be explicit
     ✓ BookingStatus enum in schemas/booking.py (single source of truth, Rules D3)
     ✓ ALLOWED_TRANSITIONS dict enforces all transitions (Rules W1)
     ✓ States: draft, collecting_details, pending_advisor_approval, approved,
               rejected, confirmation_sent, cancelled, completed

P5.5 Cancellation handling must be safe
     ✓ CANCELABLE_STATES checked before any cancel attempt
     ✓ Already-cancelled → 200 idempotent (not an error)
     ✓ Non-existent → 404 with booking_not_found code
     ✓ Non-cancelable terminal state → 422 with booking_invalid_transition code

---

Key failure/edge cases (Docs/Failures&EdgeCases.md Phase 5)

Duplicate booking submission
  Prevention: idempotency_key field on BookingCreateRequest (optional)
  Memory mode: InMemoryBookingRepository._by_idempotency dict
  Supabase mode: bookings.idempotency_key UNIQUE INDEX (phase5_schema.sql)
  Response: 409 with existing booking in data.booking_id so client can reconcile

Timezone ambiguity
  All preferred_time values are documented as IST (HH:MM 24h)
  display_timezone field is always present in every API response
  Timestamps stored as UTC; no mixed-zone comparisons in code

Cancel for non-existent booking
  Returns 404 with code=booking_not_found and a plain-language message

Cancel for already-cancelled booking
  Returns 200 (idempotent) with code=booking_already_cancelled in errors[]
  data still contains the full booking so the client has current state

Invalid state transition
  Returns 422 with code=booking_invalid_transition
  Error message includes the current status value

---

Supabase mode persistence notes

Tables applied: infra/supabase/phase5_schema.sql
  bookings        — full booking row, idempotency_key stored with UNIQUE constraint
  booking_events  — immutable audit log; one row per state transition

booking_events is written by SupabaseBookingRepository:
  create()       → from_status=NULL,  to_status=pending_advisor_approval
  update_status() → from_status=<old>, to_status=<new>
  Failures in event logging are non-blocking (logged as warning, not exception)

---

Regression check

Phase 1 eval: 100.0% (run 2026-04-30, no regressions)
Phase 3 eval: 100.0% (run 2026-04-30, no regressions)

---

Ready for Phase 6?  YES

The following are in place for Phase 6 to extend:
- BookingStatus enum includes approved, rejected, confirmation_sent, completed
- ALLOWED_TRANSITIONS covers all Phase 6 advisor paths
- booking_events audit table is live and written by Supabase repo
- booking_id format (BK-YYYYMMDD-XXXX) is stable
- Schemas/repos/services are isolated; advisor_workflow_service can import
  BookingStatus and the repository protocol without modification
