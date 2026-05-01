"""Auth APIs (Phase 7).

Implements a minimal Google OAuth login + callback to store tokens in Supabase.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.config import get_settings
from app.services.google_oauth_service import build_login_url, exchange_code_and_store_tokens

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth")


@router.get("/google/login")
async def google_login() -> RedirectResponse:
    settings = get_settings()
    try:
        url, _state = build_login_url(settings)
    except Exception as exc:
        logger.exception("oauth_login_error", exc_info=exc)
        raise HTTPException(status_code=400, detail="oauth_error") from exc
    return RedirectResponse(url=url, status_code=302)


@router.get("/google/callback")
async def google_callback(code: str = Query(...)) -> JSONResponse:
    settings = get_settings()
    try:
        data = await exchange_code_and_store_tokens(settings=settings, code=code)
    except Exception as exc:
        logger.exception("oauth_callback_error", exc_info=exc)
        raise HTTPException(status_code=400, detail="oauth_error") from exc
    return JSONResponse(status_code=200, content={"success": True, "message": "oauth_connected", "data": data, "errors": []})