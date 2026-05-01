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
from app.services.scheduler_service import send_latest_pulse_to_subscribers
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

    Phase 7: uses the same sending path as the scheduler webhook.
    """
    settings = get_settings()
    result = await send_latest_pulse_to_subscribers(settings=settings, correlation_id=None)
    return APIEnvelope(success=True, message="pulse_send_triggered", data=result)


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
