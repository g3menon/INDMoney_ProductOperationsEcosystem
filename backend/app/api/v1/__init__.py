from fastapi import APIRouter

from app.api.v1 import chat, dashboard, evals, health, pulse


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(dashboard.router, tags=["dashboard"])
api_router.include_router(pulse.router, tags=["pulse"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(evals.router, tags=["evals"])
