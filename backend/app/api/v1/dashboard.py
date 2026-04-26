"""`GET /api/v1/dashboard/badges` — badge architecture (`Docs/Architecture.md`)."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.common import APIEnvelope
from app.schemas.dashboard import BadgePayload
from app.services.badge_service import compute_badges

router = APIRouter(prefix="/dashboard")


@router.get("/badges", response_model=APIEnvelope[BadgePayload])
async def get_badges() -> APIEnvelope[BadgePayload]:
    settings = get_settings()
    payload = await compute_badges(settings)
    return APIEnvelope(success=True, message="badges", data=payload)
