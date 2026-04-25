# Groww Product Operations Ecosystem — Lean Runbook

This runbook is the minimum operational guide for running, validating, troubleshooting, and recovering the Groww Product Operations Ecosystem.

Use it during:
- local setup,
- deployment,
- smoke testing,
- incident recovery,
- and demo prep.

## System map

- **Frontend:** Next.js on Vercel
- **Backend:** FastAPI on Render
- **Database:** Supabase
- **LLM providers:** Gemini and/or Groq
- **Google integrations:** Gmail, Calendar, Sheets
- **Scheduler:** GitHub Actions and/or backend internal trigger

## Key docs

Keep these aligned:
- `Docs/Architecture.md`
- `Docs/Rules.md`
- `Docs/Failures&EdgeCases.md`
- `Docs/Runbook.md`
- `.env.example`

## Required env groups

### Frontend
```env
NEXT_PUBLIC_API_BASE_URL=
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

### Backend
```env
APP_ENV=
LOG_LEVEL=
API_BASE_URL=
FRONTEND_BASE_URL=
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
GEMINI_API_KEY=
GROQ_API_KEY=
GOOGLE_PROJECT_ID=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=
GOOGLE_OAUTH_SCOPES=
GOOGLE_AUTHORIZED_EMAIL=
GMAIL_SENDER_EMAIL=
GOOGLE_CALENDAR_ID=
GOOGLE_SHEETS_SPREADSHEET_ID=
GOOGLE_SHEETS_WORKSHEET_NAME=
TOKEN_ENCRYPTION_KEY=
SCHEDULER_SHARED_SECRET=
DEFAULT_TIMEZONE=Asia/Kolkata
```

### GitHub Actions
```env
SCHEDULER_SHARED_SECRET=
BACKEND_SCHEDULER_URL=
```

## Startup sequence

### Local
1. Verify env files are present and complete.
2. If you run **Groww Play Store** collection or other **Playwright** jobs locally, install browser binaries once (`playwright install` for the active Python environment) and confirm the script entrypoint in `Docs/Architecture.md` / `scripts/`.
3. Start backend.
4. Confirm backend health endpoint works.
5. Start frontend.
6. Confirm frontend can reach backend.
7. Open Customer, Product, and Advisor tabs.

### Groww Play Store reviews (Playwright) and RAG corpus

Use this when refreshing **Weekly Pulse** inputs or **RAG** MF/fee indexes.

1. **Play Store (Groww)**  
   - Run the documented job (for example `scripts/fetch_groww_playstore_reviews.py`).  
   - Confirm log lines show **parse count** and any **selector warnings**.  
   - Verify raw or normalized rows landed in the DB (or staging path) before pulse generation.

2. **Normalization**  
   - Ensure the normalization step completed for the batch (dedupe counts, dropped-row reasons in logs).  
   - On failure, fix upstream data or filters; do not run pulse or index rebuild on half-normalized batches without an explicit recovery plan.

3. **Chunking and RAG index (MF/fee scraped sources)**  
   - Run `ingest_sources.py` / pipeline as documented.  
   - Run `rebuild_index.py` (or equivalent) after source updates.  
   - Spot-check one retrieved chunk in dev: no raw HTML, citation metadata present.

4. **Pulse**  
   - Run pulse generation only after review ingestion + normalization succeeded for the intended window, or explicitly accept an empty-ingestion degraded mode.

### Production
1. Confirm Render env vars are correct.
2. Confirm Vercel env vars are correct.
3. Deploy backend.
4. Verify health endpoint.
5. Deploy frontend.
6. Verify dashboard load and API connectivity.

## Smoke test checklist

Run this after major changes or deploys.

- [ ] Frontend loads.
- [ ] Backend health endpoint works.
- [ ] Customer tab loads.
- [ ] Product tab loads.
- [ ] Advisor tab loads.
- [ ] One customer chat request works.
- [ ] One booking path works.
- [ ] One advisor approval/rejection action works.
- [ ] One Product Pulse path works.
- [ ] Groww Play Store ingestion path works (or documented skip) when pulse inputs changed.
- [ ] One integration path works if affected.
- [ ] Scheduler/manual trigger works if affected.

## Main incident checks

### Groww Play Store ingestion or Playwright job fails
Check:
- job logs (selector errors, timeout, zero parse count)
- Playwright and browser versions match CI or Render image
- network egress from runner (local, Render, or GitHub Actions)

Fix:
- update selectors or wait conditions per `Docs/Failures&EdgeCases.md`
- reinstall browsers if image changed
- rerun normalization only after raw batch is verified

### Frontend cannot reach backend
Check:
- `NEXT_PUBLIC_API_BASE_URL`
- backend health endpoint
- browser network errors
- CORS settings

Fix:
- correct frontend env var
- restore backend
- update CORS config if needed

### Backend fails to boot
Check:
- Render logs
- missing env vars
- config validation
- import/runtime errors

Fix:
- correct env vars
- fix startup code
- redeploy

### Supabase failures
Check:
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- DB schema existence
- backend logs

Fix:
- correct keys/config
- repair schema
- redeploy if needed

### Google OAuth fails
Check:
- redirect URI
- client ID/secret
- scopes
- connected account

Fix:
- correct Google Cloud config
- reconnect Google account
- redeploy backend if callback env changed

### Gmail / Calendar / Sheets fail
Check:
- token validity
- required scopes
- sender/calendar/sheet IDs
- backend integration logs

Fix:
- reconnect OAuth
- correct provider IDs
- retry safely only after checking duplicate risk

### Scheduler fails or runs twice
Check:
- `SCHEDULER_SHARED_SECRET`
- `BACKEND_SCHEDULER_URL`
- GitHub Actions logs
- backend duplicate protection

Fix:
- correct secrets
- rerun safely
- verify idempotency

## Rollback rules

### Frontend rollback
Use when a Vercel deploy breaks production UI.

Steps:
1. Identify last healthy deployment.
2. Roll back to it.
3. Verify dashboard and tab load.
4. Investigate bad deploy after service is restored.

### Backend rollback
Use when a Render deploy breaks API or integrations.

Steps:
1. Revert to a known good commit/config.
2. Redeploy backend.
3. Verify health endpoint.
4. Verify one DB-backed route.
5. Verify one affected integration route.

## Manual trigger paths

### Manual pulse generation
Use when scheduler fails or Product tab needs validation.

Check:
- backend healthy
- **Groww Play Store** ingestion + normalization completed for the intended date range (or explicitly accept empty-ingestion mode)
- source data exists
- generation creates exactly one expected result

### Manual scheduler trigger
Use when scheduled run did not execute.

Check:
- secret matches
- URL correct
- logs show one run only

### Manual OAuth reconnect
Use when tokens expire or wrong account is connected.

Check:
- correct Google account
- required scopes granted
- one Gmail/Calendar/Sheets action works after reconnect

## Safe mode

Use safe mode when integrations are unstable but the core product should remain usable.

Possible safe-mode actions:
- disable scheduler
- disable outbound email sends
- disable Calendar creation
- disable Sheets append
- keep dashboard read-only if needed

Rule:
- preserve workflow truth first,
- restore side effects second.

## Recovery verification

After any fix, verify:
- [ ] frontend loads
- [ ] backend health endpoint works
- [ ] all three tabs render
- [ ] one customer action works
- [ ] one product action works
- [ ] one advisor action works
- [ ] affected integration path works if relevant
- [ ] no duplicate records or side effects were created

## Escalate when

Escalate if:
- rollback does not restore service,
- production data integrity may be affected,
- duplicate emails/events/sheet rows may have been created,
- OAuth/secrets may have been exposed,
- or the failure cannot be explained quickly.

When escalating, capture:
- symptom,
- environment,
- timestamps,
- logs,
- recent changes,
- current mitigation,
- exact reproduction steps.

## Update this runbook when

Update the file whenever:
- a new external integration is added,
- a deploy/setup step changes,
- a new manual recovery path is introduced,
- a scheduler flow changes,
- **Playwright** or **ingestion/normalization/index** commands change,
- or an incident reveals a missing operational step.