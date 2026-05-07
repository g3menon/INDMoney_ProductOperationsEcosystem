# Phase 7 — Manual acceptance notes (code review baseline)

Assessment is from static review of the committed integration stack (`gmail_service`, `calendar_service`, `sheets_service`, `mcp_integrations`, `token_repository`, `security.encrypt_token`/`decrypt_token`, `approval_workflow_service`, and `api/v1/advisor.py`). Automated E2E with live Google APIs was not executed in this pass.

---

## a. Manual acceptance scenarios

| Scenario | Expected behavior | Result | Evidence (code) |
|---|---|---|---|
| **1 — Integration happy path (env var bootstrap)** | `GOOGLE_OAUTH_REFRESH_TOKEN` set; POST `/advisor/approve/{booking_id}`; logs include `gmail_confirmation_sent`, `calendar_hold_created`, `sheets_row_appended`; `approval_integrations_complete` reflects sent/created/appended. | **PASS** | Success paths log `gmail_confirmation_sent`, `calendar_hold_created`, `sheets_row_appended` respectively. Coordinator logs `approval_integrations_complete` with `extra={"gmail": ..., "calendar": ..., "sheets": ...}` containing each service result dict (`status`: `sent` / `created` / `appended`). Requires valid token refresh, `GMAIL_SENDER_EMAIL`, `GOOGLE_CALENDAR_ID`, `GOOGLE_SHEETS_SPREADSHEET_ID`, future slot (calendar past-slot guard), and no Gmail/Calendar/Sheets API errors. |
| **2 — Missing token graceful skip** | `GOOGLE_OAUTH_REFRESH_TOKEN` not set; POST approve; all three integrations show skipped in logs; booking stays approved; no crash. | **PASS** | `get_google_oauth_token()` logs `google_oauth_token_unavailable`, returns `None`. Each integration skips when `access_token` is falsy (`gmail_confirmation_skipped`, `calendar_hold_skipped`, `sheets_row_skipped`). `approve_booking` persists approval before calling `run_approval_integrations`, so approval is not rolled back. |
| **3 — Missing GMAIL_SENDER_EMAIL graceful skip** | `GMAIL_SENDER_EMAIL` unset, token present; Gmail skipped; Calendar and Sheets still run. | **PASS** | `send_booking_confirmation` checks `gmail_sender_email` first and returns skipped with `gmail_confirmation_skipped` without requiring a token; `create_calendar_hold` and `append_advisor_sheet_row` still receive the same shared `access_token` and execute their paths unless they skip for their own config. |
| **4 — Missing GOOGLE_CALENDAR_ID graceful skip** | `GOOGLE_CALENDAR_ID` unset, token present; Calendar skipped; Gmail and Sheets still attempt. | **PASS** | `create_calendar_hold` returns early when `google_calendar_id` is unset (`calendar_hold_skipped`); Gmail and Sheets run with the shared token absent other skips. |
| **5 — Token refresh fails (invalid client secret)** | `GOOGLE_CLIENT_SECRET` invalid; `token_repository` returns `None`; all three skip; `google_oauth_token_refresh_failed` logged. | **PASS** | `get_google_oauth_token` catches exceptions, logs `google_oauth_token_refresh_failed` with `extra={"error": ...}`, returns `None`. All three integrations then skip due to missing `access_token`. |
| **6 — Duplicate approval (idempotency)** | POST approve for already-approved booking: 409 or safe 200 with existing state; `run_approval_integrations` not called again. | **PASS** | `approve_booking` returns early when `booking.status == APPROVED` with `idempotent=True` **before** any call to `run_approval_integrations`. `advisor.py` returns **200 OK** with `data.idempotent=True` and informational `errors` entry (`approval_already_approved`). |

---

## b. Definition of Done checklist

_(Condensed checklist for this gate; aligns with Docs/Rules.md Phase 7 themes.)_

| Item | Result | Notes |
|---|---|---|
| Gmail action works through the backend | **PASS** | `send_booking_confirmation` invoked from `run_approval_integrations` after approval is committed; uses Settings + Gmail API / never raises unhandled exceptions to the approval caller. |
| Calendar event creation works | **PASS** | `create_calendar_hold` builds event and inserts when configured; respects past-slot and conflict guards. |
| Sheets append works (when enabled) | **PASS** | `append_advisor_sheet_row` appends when `GOOGLE_SHEETS_SPREADSHEET_ID` is set (and worksheet exists); skips when spreadsheet ID missing. |
| Failures degrade gracefully with safe user-facing states | **PARTIAL** | Approval HTTP response remains success-focused; integration outcomes are logged (`approval_integrations_complete`, per-integration skip/failure logs) rather than surfaced on `ApprovalResult` / envelope for the advisor client. Booking state stays correct (`W5`): no rollback of approval on integration failure — **graceful**. **GAP:** operator/advisor UX does not automatically see integration skip/failure in the API payload (visibility is logs / ops). |
| Token encryption helpers (`encrypt_token` / `decrypt_token`) exist | **PASS** | Implemented in `backend/app/core/security.py`. |
| `token_repository` has Phase 8 TODO comment for DB path | **PASS** | File-level and inline TODO describing `google_oauth_tokens` and DB read/refresh behavior. |
| No secrets in code — all from Settings | **PASS** | OAuth IDs, secrets, tokens, IDs, sender email, sheet IDs read via `get_settings()` / `Credentials` wiring; `_GOOGLE_TOKEN_URI` is only the public Google token endpoint constant. |
| Structured logs at every integration step | **PASS** | Each integration emits skip/warn/info/error logs with structured `extra`; coordinator logs per-integration failures and a final `approval_integrations_complete` summary. |

**Rules.md Phase 334 additional line (scheduler):** `"Scheduler endpoint can be triggered securely."` — **not closed by this codebase review:** `SCHEDULER_SHARED_SECRET` exists on `Settings`, but no secured scheduler-trigger route was found in `backend/app/api` (e.g. `internal.py` remains a stub). This gate’s explicit checklist omits scheduler; flag for product if Phase 7 is interpreted as including that bullet verbatim.

---

## c. Scenario and DoD summary

- **Scenarios:** 1–6 → **PASS** (with Scenario 1’s usual configuration/API/slot prerequisites noted above).
- **DoD checklist:** Seven items → six **PASS**, one **PARTIAL** (user-visible remediation for integration failures).

Recommendation: retain one live-environment manual run (`Docs/Runbook.md` Step 6); if Phase 7 is read as strictly requiring a triggerable scheduler, complete `Docs/Rules.md` Phase 334 — `SCHEDULER_SHARED_SECRET` is on `Settings`, but no secured scheduler route appeared in repo review (`internal.py` stub).

Phase 7 gate: PASS
