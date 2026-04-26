"""CLI entrypoint for eval suites (`python -m app.evals.run_all --phase 1`)."""

from __future__ import annotations

import argparse
import os
import sys
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run automated eval suites.")
    parser.add_argument("--phase", type=int, default=1, help="Phase number (default: 1).")
    args = parser.parse_args(argv)

    if args.phase != 1:
        print("Only phase 1 is implemented in this repository snapshot.", file=sys.stderr)
        return 2

    _ensure_eval_env()

    # Stable offline run: avoid real network calls for Supabase fixtures.
    with patch(
        "app.integrations.supabase.client.check_supabase_connectivity",
        new=AsyncMock(return_value=(True, "ok")),
    ):
        from app.evals.phase1_checks import run_phase1_evals

        report = run_phase1_evals()

    print(report.model_dump_json(indent=2))
    if report.score < 85.0:
        print(f"\nFAIL: score {report.score}% is below 85%.", file=sys.stderr)
        return 1
    print(f"\nPASS: score {report.score}% (threshold 85%).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
