"""Supabase connectivity checks (Phase 1). Full DB access comes in later phases."""

from __future__ import annotations

import logging
from typing import Tuple

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


async def check_supabase_connectivity(settings: Settings) -> Tuple[bool, str]:
    """
    Validate reachability of the configured Supabase project (GoTrue health).
    Uses service role key only server-side; never log the key (O5).
    """
    base = settings.supabase_url.rstrip("/")
    url = f"{base}/auth/v1/health"
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        logger.warning("supabase_connectivity_network_error", extra={"correlation_id": "-"})
        return False, f"network_error: {type(exc).__name__}"

    if resp.status_code >= 400:
        return False, f"http_{resp.status_code}"

    return True, "ok"
