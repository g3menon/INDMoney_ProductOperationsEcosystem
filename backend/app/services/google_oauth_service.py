"""Google OAuth service — Phase 7.

Provides the OAuth login URL and handles the callback exchange to persist
encrypted tokens into Supabase (`google_oauth_tokens`).
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import httpx
from supabase import Client, create_client

from app.core.config import Settings
from app.core.security import encrypt_token

logger = logging.getLogger(__name__)

_AUTH_BASE = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def build_login_url(settings: Settings) -> tuple[str, str]:
    """Return (url, state)."""
    if not settings.google_client_id or not settings.google_redirect_uri:
        raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_REDIRECT_URI must be configured")

    scope_str = settings.google_oauth_scopes or ""
    if not scope_str.strip():
        raise ValueError("GOOGLE_OAUTH_SCOPES must be configured")

    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": scope_str,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{_AUTH_BASE}?{urllib.parse.urlencode(params)}", state


def _get_supabase(settings: Settings) -> Client:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise ValueError("Supabase not configured")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


async def exchange_code_and_store_tokens(
    *,
    settings: Settings,
    code: str,
) -> dict[str, Any]:
    """Exchange OAuth code for tokens and store them encrypted in Supabase."""
    if not settings.google_client_id or not settings.google_client_secret or not settings.google_redirect_uri:
        raise ValueError("Google OAuth client config missing")
    if not settings.token_encryption_key:
        raise ValueError("TOKEN_ENCRYPTION_KEY missing")

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        payload = resp.json()

    refresh_token = payload.get("refresh_token")
    access_token = payload.get("access_token")
    expires_in = int(payload.get("expires_in") or 0)

    if not refresh_token:
        # If the user previously consented, Google may omit refresh_token unless prompt=consent
        raise ValueError("refresh_token not returned; ensure prompt=consent and access_type=offline")

    authorized_email = settings.google_authorized_email or "default"
    expires_at = (_now_utc().timestamp() + expires_in) if expires_in else None
    expires_at_iso = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat() if expires_at else None

    row = {
        "authorized_email": authorized_email,
        "scopes": settings.google_oauth_scopes or "",
        "encrypted_refresh_token": encrypt_token(str(refresh_token), settings.token_encryption_key),
        "encrypted_access_token": encrypt_token(str(access_token), settings.token_encryption_key) if access_token else None,
        "access_token_expires_at": expires_at_iso,
        "updated_at": _now_utc().isoformat(),
    }

    sb = _get_supabase(settings)
    await asyncio.to_thread(lambda: sb.table("google_oauth_tokens").upsert(row, on_conflict="authorized_email").execute())

    logger.info("google_oauth_tokens_stored", extra={"authorized_email": authorized_email})
    return {
        "authorized_email": authorized_email,
        "access_token_present": bool(access_token),
        "expires_in": expires_in,
    }
