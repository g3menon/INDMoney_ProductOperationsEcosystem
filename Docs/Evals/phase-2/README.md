Phase 2 eval artifacts

- Automated: `cd backend; python -m app.evals.run_all --phase 2`
- Manual happy path (text-only):
  1. Run Playwright collector.
  2. Run ingestion (`scripts/ingest_sources.py`).
  3. Generate pulse (`POST /api/v1/pulse/generate` with `use_fixture=false`).
  4. Verify Product tab shows current + history + subscription UI states.
