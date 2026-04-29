Phase 7 eval artifacts — External integrations (Gmail/Calendar/Sheets) + scheduler

Automated
- Not available in `backend/app/evals/run_all.py` yet.

Manual acceptance gate (text-only, before voice / Phase 8)
- Run `Docs/Runbook.md` End-to-end test → Step 6 (Integrations, when Phase 7 is in scope).
- Validate `Docs/Rules.md` Phase 7 “Definition of Done”:
  - Gmail action works through the backend
  - Calendar event creation works
  - Sheets append works (when enabled)
  - failures degrade gracefully with safe user-facing states

Validate key failures in `Docs/Failures&EdgeCases.md` (Phase 7 section):
- OAuth redirect URI mismatch / missing scopes
- expired/revoked tokens
- duplicate side effects on retries (email/calendar/sheets)
- scheduler triggered twice (cron/manual overlap)

Record
- Screenshots/notes/log excerpts in this folder for:
  - one integration happy path
  - one integration failure + recovery (or safe-mode behavior)

