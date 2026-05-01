"""Internal APIs (Phase 7).

Contains scheduler webhook endpoints intended to be called by GitHub Actions cron
or manually during recovery (Docs/Runbook.md).
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter
from fastapi import Header, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.services.scheduler_service import send_latest_pulse_to_subscribers

router = APIRouter(prefix="/internal")


def _expect_bearer(auth: str | None) -> str | None:
    if not auth:
        return None
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None


@router.post("/scheduler/pulse")
async def scheduler_pulse(
    authorization: str | None = Header(default=None),
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
) -> JSONResponse:
    """Trigger weekly pulse email send to all active subscribers.

    Protected by `SCHEDULER_SHARED_SECRET` using Bearer auth.
    """
    settings = get_settings()
    secret = settings.scheduler_shared_secret
    token = _expect_bearer(authorization)

    if not secret:
        raise HTTPException(status_code=501, detail="scheduler_not_configured")
    if not token or not secrets.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="unauthorized")

    result = await send_latest_pulse_to_subscribers(settings=settings, correlation_id=x_correlation_id)
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "scheduler_pulse_triggered",
            "data": result.model_dump(),
            "errors": [],
        },
    )
