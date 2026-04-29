"""Voice APIs — stub (Phase 8)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/voice")


@router.get("")
async def voice_root() -> JSONResponse:
    return JSONResponse(status_code=501, content={"detail": "not_implemented_phase_8"})
