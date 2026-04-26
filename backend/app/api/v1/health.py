"""`GET /api/v1/health` — liveness and safe config snapshot."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.dependencies import CorrelationIdDep
from app.integrations.supabase.client import check_supabase_connectivity
from app.schemas.common import APIEnvelope

router = APIRouter()


@router.get("/health", response_model=APIEnvelope[dict[str, Any]])
async def health(correlation_id: CorrelationIdDep) -> APIEnvelope[dict[str, Any]]:
    settings = get_settings()
    ok, supa_msg = await check_supabase_connectivity(settings)
    data = {
        "status": "ok" if ok else "degraded",
        "correlation_id": correlation_id,
        "supabase": {"reachable": ok, "detail": supa_msg if not ok else "ok"},
        "settings": settings.safe_public_dict(),
    }
    return APIEnvelope(success=True, message="health", data=data)
