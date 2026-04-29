"""Auth APIs — stub (Phase 4)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/auth")


@router.get("")
async def auth_root() -> JSONResponse:
    return JSONResponse(status_code=501, content={"detail": "not_implemented_phase_4"})
