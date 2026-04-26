"""FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings


def get_correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "unknown")


SettingsDep = Annotated[Settings, Depends(get_settings)]
CorrelationIdDep = Annotated[str, Depends(get_correlation_id)]
