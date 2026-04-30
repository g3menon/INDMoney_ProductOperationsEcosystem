Phase 5 eval artifacts — Booking and customer workflow state

Status: PASS (automated score 100.0% — threshold 85%)

---

Automated eval suite

Run command:
  cd backend
  python -m app.evals.run_all --phase 5

Suite: backend/app/evals/phase5_checks.py
Artifact: Deliverables/Evals/phase-5/latest.json

Checks and weights:
  openapi_booking_paths       20 pts — POST /create, GET /{id}, POST /cancel in OpenAPI spec
  create_booking_happy_path   30 pts — 201 response, BK- prefix ID, pending_advisor_approval status, timezone label
  get_booking_by_id           20 pts — GET round-trip returns persisted booking
  cancel_booking_happy_path   15 pts — POST /cancel transitions to cancelled, reason persisted
  duplicate_submit_idempotent 10 pts — same idempotency_key → 409 + existing booking_id in data
  invalid_cancel_errors_safe   5 pts — non-existent 404 (booking_not_found), already-cancelled 200 idempotent

Latest run: 100.0 / 100 (2026-04-30)

---

Manual acceptance gate (text-only, before voice / Phase 8)

Run Docs/Runbook.md End-to-end test → Step 4 (Booking).

Validate the Docs/Rules.md Phase 5 "Definition of Done":
- booking can be created from the customer flow            ✓ automated
- booking state is stored and reflected                    ✓ automated (memory) / SQL migration for Supabase
- cancel flow works                                        ✓ automated
- invalid transitions are handled gracefully               ✓ automated

Validate key failure/edge cases from Docs/Failures&EdgeCases.md (Phase 5 section):
- duplicate booking submission is prevented                ✓ automated (idempotency_key, 409)
- timezone clarity is consistent                           ✓ display_timezone field in every response
- invalid cancel: non-existent / already-cancelled         ✓ automated

---

Storage modes

Memory (default, APP_ENV=eval/test/dev):
  Set BOOKING_STORAGE_MODE=memory or leave unset.
  Resets on restart. Used by automated evals.

Supabase (production):
  1. Apply infra/supabase/phase5_schema.sql to your Supabase project.
  2. Set BOOKING_STORAGE_MODE=supabase in your .env.
  3. The bookings table stores idempotency_key with a unique index.
  4. The booking_events table receives an audit row on every state transition.

---

Record

See ACCEPTANCE_NOTES.md in this folder for the full Phase 5 closure summary.
