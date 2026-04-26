"""Aggregated HTTP routers (optional indirection per `Docs/Architecture.md`)."""

from app.api.v1 import api_router

__all__ = ["api_router"]
