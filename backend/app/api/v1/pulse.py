"""Weekly Pulse APIs (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.repositories.subscription_repository import get_subscription_repository
from app.schemas.common import APIEnvelope
from app.schemas.pulse import (
    PulseGenerateRequest,
    SendNowResult,
    SubscribeRequest,
    SubscribeResult,
    WeeklyPulse,
)
from app.services.pulse_workflow_service import generate_weekly_pulse, get_current_pulse, get_pulse_history

router = APIRouter(prefix="/pulse")


@router.post("/generate", response_model=APIEnvelope[WeeklyPulse])
async def generate(body: PulseGenerateRequest | None = None) -> APIEnvelope[WeeklyPulse]:
    settings = get_settings()
    body = body or PulseGenerateRequest()
    pulse = await generate_weekly_pulse(settings, body)
    return APIEnvelope(success=True, message="pulse_generated", data=pulse)


@router.get("/current", response_model=APIEnvelope[WeeklyPulse | None])
async def current() -> APIEnvelope[WeeklyPulse | None]:
    settings = get_settings()
    pulse = await get_current_pulse(settings)
    return APIEnvelope(success=True, message="pulse_current", data=pulse)


@router.get("/history", response_model=APIEnvelope[list[WeeklyPulse]])
async def history(limit: int = 20) -> APIEnvelope[list[WeeklyPulse]]:
    settings = get_settings()
    rows = await get_pulse_history(settings, limit=limit)
    return APIEnvelope(success=True, message="pulse_history", data=rows)


@router.post("/send-now", response_model=APIEnvelope[SendNowResult])
async def send_now() -> APIEnvelope[SendNowResult]:
    """Trigger an immediate pulse send to all active subscribers.

    Phase 2: loads latest pulse and active subscriber list, returns a mock
    queued response. Actual Gmail MCP delivery is wired in Phase 7.
    """
    settings = get_settings()
    pulse = await get_current_pulse(settings)
    pulse_id = pulse.pulse_id if pulse else "no-pulse"

    sub_repo = get_subscription_repository(settings)
    # Retrieve active subscriber emails; fall back gracefully if none.
    try:
        active_emails: list[str] = []
        if hasattr(sub_repo, "active"):
            active_emails = list(sub_repo.active)  # type: ignore[attr-defined]
        else:
            active_emails = []
    except Exception:
        active_emails = []

    return APIEnvelope(
        success=True,
        message="pulse_send_queued",
        data=SendNowResult(sent_to=active_emails, pulse_id=pulse_id, status="queued"),
    )


@router.post("/subscribe", response_model=APIEnvelope[SubscribeResult])
async def subscribe(body: SubscribeRequest) -> APIEnvelope[SubscribeResult]:
    settings = get_settings()
    repo = get_subscription_repository(settings)
    email, status = await repo.subscribe(str(body.email))
    return APIEnvelope(success=True, message="subscribed", data=SubscribeResult(email=email, status=status))


@router.post("/unsubscribe", response_model=APIEnvelope[SubscribeResult])
async def unsubscribe(body: SubscribeRequest) -> APIEnvelope[SubscribeResult]:
    settings = get_settings()
    repo = get_subscription_repository(settings)
    email, status = await repo.unsubscribe(str(body.email))
    return APIEnvelope(success=True, message="unsubscribed", data=SubscribeResult(email=email, status=status))
