Phase 5 eval artifacts — Booking and customer workflow state

Automated
- Not available in `backend/app/evals/run_all.py` yet.

Manual acceptance gate (text-only, before voice / Phase 8)
- Run `Docs/Runbook.md` End-to-end test → Step 4 (Booking).
- Validate the `Docs/Rules.md` Phase 5 “Definition of Done”:
  - booking can be created from the customer flow
  - booking state is stored and reflected in the UI
  - cancel flow works
  - invalid transitions are handled gracefully

Validate the key failure/edge cases from `Docs/Failures&EdgeCases.md` (Phase 5 section):
- duplicate booking submission is prevented (or safely idempotent)
- timezone clarity is consistent (display and confirmation)
- invalid cancel requests (non-existent / already cancelled / wrong state) show safe user-facing errors

Record
- Screenshots/notes in this folder for:
  - one booking happy path
  - one duplicate-submit attempt
  - one invalid cancel attempt

