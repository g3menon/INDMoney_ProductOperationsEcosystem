Phase 6 eval artifacts — Advisor HITL approval

Automated
- Not available in `backend/app/evals/run_all.py` yet.

Manual acceptance gate (text-only, before voice / Phase 8)
- Run `Docs/Runbook.md` End-to-end test → Step 5 (Advisor: pending/upcoming lists + approve/reject).
- Validate the `Docs/Rules.md` Phase 6 Definition of Done:
  - pending approvals are visible
  - advisor can approve or reject
  - shared state updates keep Customer and Advisor views coherent

Validate the targeted failures in `Docs/Failures&EdgeCases.md` (Phase 6 section):
- double-click / duplicate approval attempts are idempotent
- approve/reject results refresh correctly (advisor and customer agree on shared status)
- advisor has enough context (no “blank” or missing-summary scenarios)

Record
- Screenshots/notes in this folder for:
  - approve happy path (including confirmation preview behavior)
  - reject happy path (with reason capture if required by your current UX)
  - a duplicate-approval attempt

