This folder holds **manual and automated** eval artifacts by phase (see `Docs/Rules.md` EVAL* and `Docs/Runbook.md` Recording).

- `phase-1/`: connectivity + config + health + badges (automated evals available)
- `phase-2/`: weekly pulse ingestion + normalization + pulse APIs + Product tab rendering (automated evals available)
- `phase-3/`: customer text chat foundation (automated evals available)
- `phase-4/`..`phase-7/`: manual acceptance gates (no automated eval harness in `app.evals.run_all` yet)

For local runs:
- Phase 1: `cd backend; python -m app.evals.run_all --phase 1`
- Phase 2: `cd backend; python -m app.evals.run_all --phase 2`
- Phase 3: `cd backend; python -m app.evals.run_all --phase 3`

Notes:
- The eval CLI currently supports **only phases 1, 2, and 3** (see `backend/app/evals/run_all.py`).
- For phases 4–7, record results under the corresponding `phase-<n>/` folder after running the text-only end-to-end checklist in `Docs/Runbook.md` (before voice / Phase 8).
