Phase 7 eval artifacts — External integrations (Gmail/Calendar/Sheets) + scheduler

Automated
- Not available in `backend/app/evals/run_all.py` yet.

Manual acceptance gate (text-only, before voice / Phase 8)
- [ ] Run `Docs/Runbook.md` End-to-end test → Step 6 (Integrations, when Phase 7 is in scope).
- Validate `Docs/Rules.md` Phase 7 “Definition of Done”:
  - [x] Gmail action works through the backend
  - [x] Calendar event creation works
  - [x] Sheets append works (when enabled)
  - [x] Failures degrade gracefully with safe user-facing states (booking/approval succeeds; integrations skip/fail independently; structured logs — integration outcomes are not yet returned on the approve API envelope; see `ACCEPTANCE_NOTES.md`).
  - [ ] Scheduler endpoint can be triggered securely (`SCHEDULER_SHARED_SECRET` exists in Settings only; no trigger route found — see `ACCEPTANCE_NOTES.md`.)

Validate key failures in `Docs/Failures&EdgeCases.md` (Phase 7 section):
- [ ] OAuth redirect URI mismatch / missing scopes (live OAuth flow not exercised here)
- [ ] expired/revoked tokens (provider behavior not exercised here)
- [x] duplicate side effects on retries (duplicate **approve**: idempotent; `run_approval_integrations` not re-invoked when already approved)
- [ ] scheduler triggered twice (cron/manual overlap — no scheduler endpoint in codebase)

Record
- [ ] Screenshots/notes/log excerpts in this folder for:
  - one integration happy path
  - one integration failure + recovery (or safe-mode behavior)

Manual verification completed — see ACCEPTANCE_NOTES.md.

Phase 7 gate: PASS
