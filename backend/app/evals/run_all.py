"""CLI entrypoint for eval suites (`python -m app.evals.run_all --phase 1`)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch


def _ensure_eval_env() -> None:
    """Eval CLI must be runnable without a local `.env` file (stable fixtures)."""
    os.environ.setdefault("APP_ENV", "eval")
    os.environ.setdefault("LOG_LEVEL", "warning")
    os.environ.setdefault("FRONTEND_BASE_URL", "http://localhost:3000")
    os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "eval-placeholder-service-role")
    os.environ.setdefault("PHASE1_SKIP_SUPABASE_STARTUP_CHECK", "true")
    from app.core.config import clear_settings_cache

    clear_settings_cache()


def _persist_deliverable(phase: int, report) -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    out_dir = repo_root / "Deliverables" / "Evals" / f"phase-{phase}"
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    version = getattr(report, "version", f"phase{phase}")

    payload = report.model_dump()
    payload.setdefault("generated_at", datetime.now(timezone.utc).isoformat())

    out_path = out_dir / f"eval_{ts}_{version}.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "latest.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run automated eval suites.")
    parser.add_argument("--phase", type=int, default=1, help="Phase number (default: 1).")
    args = parser.parse_args(argv)

    if args.phase not in (1, 2):
        print("Only phase 1 and 2 evals are available.", file=sys.stderr)
        return 2

    _ensure_eval_env()

    # Stable offline run: avoid real network calls for Supabase fixtures.
    with patch(
        "app.integrations.supabase.client.check_supabase_connectivity",
        new=AsyncMock(return_value=(True, "ok")),
    ):
        if args.phase == 1:
            from app.evals.phase1_checks import run_phase1_evals

            report = run_phase1_evals()
        else:
            from app.evals.pulse_checks import run_phase2_evals

            report = run_phase2_evals()

    out_path = _persist_deliverable(args.phase, report)
    print(report.model_dump_json(indent=2))
    print(f"\nSaved deliverable: {out_path}")
    if report.score < 85.0:
        print(f"\nFAIL: score {report.score}% is below 85%.", file=sys.stderr)
        return 1
    print(f"\nPASS: score {report.score}% (threshold 85%).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
