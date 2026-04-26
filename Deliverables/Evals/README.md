This folder holds **manual and automated** eval artifacts by phase (see `Docs/Rules.md` EVAL* and `Docs/Runbook.md` Recording).

- `phase-1/`: connectivity + config + health + badges
- `phase-2/`: weekly pulse ingestion + normalization + pulse APIs + Product tab rendering

For local runs:
- Phase 1: `cd backend; python -m app.evals.run_all --phase 1`
- Phase 2: `cd backend; python -m app.evals.run_all --phase 2`
