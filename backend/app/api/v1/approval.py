"""Approval APIs — stub (Phase 6)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/approval")


@router.get("")
async def approval_root() -> JSONResponse:
    return JSONResponse(status_code=501, content={"detail": "not_implemented_phase_6"})
