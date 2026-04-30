# Groww Product Operations Ecosystem

Single-repo dashboard (Next.js + FastAPI + Supabase) for **Groww** product operations: customer chat (MF + fee), weekly pulse from Play Store reviews, advisor approvals, and governed Google integrations.

- **Architecture & phases:** `Docs/Architecture.md`  
- **Implementation rules:** `Docs/Rules.md`  
- **Canonical URLs & Playwright rules:** `Deliverables/Resources.md`  
- **Ops:** `Docs/Runbook.md`  
- **Full E2E without voice:** use **End-to-end test (text-only, before voice / Phase 8)** in the runbook before depending on STT/TTS.

## Phase 1 — local smoke

1. Copy `.env.example` to `.env` and fill **backend** `FRONTEND_BASE_URL`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY` (use `PHASE1_SKIP_SUPABASE_STARTUP_CHECK=true` only if you intentionally run without Supabase).
2. From `backend/`: `python -m pip install -r requirements.txt` then `uvicorn app.main:app --reload --port 8000`.
3. From `frontend/`: set `NEXT_PUBLIC_API_BASE_URL` (e.g. `http://127.0.0.1:8000`), then `npm install` and `npm run dev`.
4. Phase 1 evals: from `backend/`, `python -m app.evals.run_all --phase 1` (must score **≥ 85%**; default fixture env is embedded for CI-style runs).

## Local setup (Windows PowerShell) — Phase 1 + Phase 2

### 0) Apply Supabase schema (one-time per project)

- In Supabase SQL editor, run: `infra/supabase/phase1_phase2_schema.sql`

### 1) Create `.env`

Copy `.env.example` → `.env` and fill at minimum:

- Backend: `APP_ENV`, `FRONTEND_BASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DEFAULT_TIMEZONE`
- Frontend: `NEXT_PUBLIC_API_BASE_URL` (and optionally Supabase public vars for later phases)

### 2) Start backend

```powershell
cd backend
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Smoke:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/dashboard/badges
```

### 3) Start frontend

```powershell
cd ..\frontend
npm install
# Next.js reads env vars from files under `frontend/` (e.g. `frontend/.env.local`),
# not the repo-root `.env`.
$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000"
npm run dev
```

### 4) Run Play Store collector (Phase 2)

```powershell
cd ..
cd backend
python -m playwright install chromium
cd ..
python scripts\fetch_groww_playstore_reviews.py --limit 200 --out reviews_raw.json
```

### 5) Ingest raw JSON into Supabase (Phase 2)

```powershell
python scripts\ingest_sources.py --in reviews_raw.json
```

### 6) Generate pulse from real ingested data (Phase 2)

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/pulse/generate -ContentType application/json -Body '{"use_fixture":false,"lookback_weeks":8}'
Invoke-RestMethod http://127.0.0.1:8000/api/v1/pulse/current
Invoke-RestMethod http://127.0.0.1:8000/api/v1/pulse/history?limit=10
```

### 7) Run automated evals

```powershell
cd backend
python -m app.evals.run_all --phase 1
python -m app.evals.run_all --phase 2
```
