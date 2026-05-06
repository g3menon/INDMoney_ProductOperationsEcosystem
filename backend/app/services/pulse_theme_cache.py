"""Read-only cache for the latest Weekly Pulse themes.
Used by customer_router_service to enrich the booking greeting (Pillar B).
This service is best-effort: if Supabase is unavailable, returns empty list."""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 1800  # 30 minutes
_cache: dict[str, object] = {}

# TODO: Create weekly_pulses table in infra/supabase/ migration before
# this service can return real data. Until then it returns [] gracefully.


def get_active_themes(settings: "Settings") -> list:
    """Return the top themes from the most recent non-degraded Weekly Pulse.

    Returns an empty list if:
    - No pulse exists
    - The latest pulse is degraded
    - The latest pulse is older than 7 days
    - The weekly_pulses Supabase table does not exist
    - Any exception occurs
    """
    global _cache

    # Serve from in-memory cache if fresh
    cached_at = _cache.get("cached_at", 0)
    if time.monotonic() - cached_at < _CACHE_TTL_SECONDS:
        cached_themes = _cache.get("themes")
        if cached_themes is not None:
            return cached_themes

    try:
        from supabase import create_client

        client = create_client(settings.supabase_url, settings.supabase_service_role_key)
        response = (
            client.table("weekly_pulses")
            .select("themes, created_at, degraded")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        rows = response.data
        if not rows:
            _set_cache([])
            return []

        row = rows[0]
        if row.get("degraded"):
            _set_cache([])
            return []

        # Staleness check: reject if older than 7 days
        from datetime import datetime, timezone
        created_raw = row.get("created_at", "")
        if created_raw:
            created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - created_at).days
            if age_days > 7:
                _set_cache([])
                return []

        raw_themes = row.get("themes") or []
        # Try to return as list of PulseTheme if schema is available
        try:
            from app.schemas.pulse import PulseTheme
            themes = [PulseTheme(**t) if isinstance(t, dict) else t for t in raw_themes]
        except Exception:
            # Fallback: return raw dicts, _build_booking_greeting uses getattr safely
            themes = raw_themes

        _set_cache(themes)
        return themes

    except Exception as exc:
        logger.warning(
            "pulse_theme_cache_unavailable",
            extra={"reason": str(exc)[:120]},
        )
        _set_cache([])
        return []


def _set_cache(themes: list) -> None:
    _cache["themes"] = themes
    _cache["cached_at"] = time.monotonic()
