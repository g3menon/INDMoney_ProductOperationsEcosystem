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
