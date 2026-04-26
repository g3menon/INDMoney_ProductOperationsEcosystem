"""
Phase 2 helper: generate a weekly pulse using fixture data.

Usage:
  python scripts/run_pulse.py
"""

from __future__ import annotations

import asyncio
import os


async def _run() -> None:
    os.environ.setdefault("APP_ENV", "eval")
    os.environ.setdefault("LOG_LEVEL", "warning")
    os.environ.setdefault("FRONTEND_BASE_URL", "http://localhost:3000")
    os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "eval-placeholder-service-role")
    os.environ.setdefault("PHASE1_SKIP_SUPABASE_STARTUP_CHECK", "true")
    os.environ.setdefault("PULSE_STORAGE_MODE", "memory")

    from app.core.config import clear_settings_cache, get_settings
    from app.schemas.pulse import PulseGenerateRequest
    from app.services.pulse_workflow_service import generate_weekly_pulse

    clear_settings_cache()
    pulse = await generate_weekly_pulse(get_settings(), PulseGenerateRequest(use_fixture=True))
    print(pulse.model_dump_json(indent=2))


def main() -> int:
    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

