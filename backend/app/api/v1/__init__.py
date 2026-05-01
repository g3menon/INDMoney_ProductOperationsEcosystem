from fastapi import APIRouter

from app.api.v1 import (
    advisor,
    approval,
    auth,
    booking,
    chat,
    dashboard,
    evals,
    health,
    internal,
    pulse,
    voice,
)


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(dashboard.router, tags=["dashboard"])
api_router.include_router(pulse.router, tags=["pulse"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(evals.router, tags=["evals"])
# Booking/advisor workflows are live; auth + internal scheduler are Phase 7.
# Voice remains a Phase 8 stub (501 until implemented).
api_router.include_router(advisor.router, tags=["advisor"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(internal.router, tags=["internal"])
api_router.include_router(booking.router, tags=["booking"])
api_router.include_router(approval.router, tags=["approval"])
api_router.include_router(voice.router, tags=["voice"])
