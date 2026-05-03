"""Weekly Pulse APIs (Phase 2)."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Header, HTTPException

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
from app.mcp.send_weekly_pulse_email import send_weekly_pulse_email
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


@router.post("/trigger", response_model=APIEnvelope[SendNowResult])
async def send_now(
    authorization: str | None = Header(default=None),
) -> APIEnvelope[SendNowResult]:
    """Trigger an immediate pulse send to all active subscribers.

    Phase 7: uses the same sending path as the scheduler webhook.
    """
    settings = get_settings()
    secret = settings.scheduler_shared_secret
    token = authorization.split(" ", 1)[1].strip() if authorization and authorization.lower().startswith("bearer ") else None
    if not secret:
        raise HTTPException(status_code=501, detail="pulse_trigger_not_configured")
    if not token or not secrets.compare_digest(token, secret):
        raise HTTPException(status_code=401, detail="unauthorized")
    result = await send_latest_pulse_to_subscribers(settings=settings, correlation_id=None)
    return APIEnvelope(success=True, message="pulse_send_triggered", data=result)


@router.post("/subscribe", response_model=APIEnvelope[SubscribeResult])
async def subscribe(body: SubscribeRequest) -> APIEnvelope[SubscribeResult]:
    settings = get_settings()
    repo = get_subscription_repository(settings)
    email, status = await repo.subscribe(str(body.email))
    pulse = await get_current_pulse(settings)
    delivery_status = "no_pulse"
    delivery_message = "Subscription saved. Generate a Weekly Pulse to send the first email."

    if pulse:
        delivery = await send_weekly_pulse_email(pulse=pulse, to_email=email, correlation_id=None)
        delivery_status = str(delivery.get("status") or "failed")
        if delivery_status == "sent":
            delivery_message = "Subscription saved and the current pulse was sent."
        elif delivery_status == "skipped":
            delivery_message = "Subscription saved. Email delivery needs workspace mail setup."
        else:
            delivery_message = "Subscription saved. The current pulse email could not be delivered."

    return APIEnvelope(
        success=delivery_status in ("sent", "skipped", "no_pulse"),
        message="subscribed",
        data=SubscribeResult(
            email=email,
            status=status,
            pulse_id=pulse.pulse_id if pulse else None,
            delivery_status=delivery_status,  # type: ignore[arg-type]
            delivery_message=delivery_message,
        ),
    )


@router.post("/unsubscribe", response_model=APIEnvelope[SubscribeResult])
async def unsubscribe(body: SubscribeRequest) -> APIEnvelope[SubscribeResult]:
    settings = get_settings()
    repo = get_subscription_repository(settings)
    email, status = await repo.unsubscribe(str(body.email))
    return APIEnvelope(success=True, message="unsubscribed", data=SubscribeResult(email=email, status=status))
