"""MCP action: get_latest_pulse_context — Phase 7.

Provides a compact, provider-safe pulse summary for downstream integrations.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.schemas.pulse import WeeklyPulse
from app.services.pulse_workflow_service import get_current_pulse


async def get_latest_pulse_context() -> WeeklyPulse | None:
    settings = get_settings()
    return await get_current_pulse(settings)
