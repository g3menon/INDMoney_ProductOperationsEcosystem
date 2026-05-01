"""Token repository — Phase 7.

Provides a Google OAuth access token for use by integration services.

Strategy:
- Primary: read encrypted tokens from `google_oauth_tokens` (Phase 7 schema),
  decrypt using TOKEN_ENCRYPTION_KEY, and return a valid access token.
- If the stored access token is missing/expired: refresh using the refresh token
  and GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET, then persist the new access token
  encrypted back into the table.
- Fallback: if no DB row exists, use GOOGLE_OAUTH_REFRESH_TOKEN env var to refresh
  and return an access token (local/dev bootstrap path).

Rules satisfied:
  I2  — OAuth credentials stay server-side only.
  D7  — tokens never persisted in plaintext (encrypted at rest).
  G7  — graceful failure: return None when unconfigured; callers skip with warning.
  G5  — no secrets in code; all values come from Settings.
"""

from __future__ import annotations

import logging
import asyncio
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from supabase import Client, create_client

from app.core.config import get_settings
from app.core.security import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)

_GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _get_supabase_client(settings) -> Client | None:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return None
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


async def get_google_oauth_token() -> str | None:
    """Return a live Google OAuth access token for integration use.

    Phase 7: reads GOOGLE_OAUTH_REFRESH_TOKEN from environment, exchanges it
    for a valid access token using GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET.

    Returns:
        A valid access token string, or None if not configured.
        Callers must treat None as "integration not configured — skip gracefully".
    """
    settings = get_settings()

    refresh_token = settings.google_oauth_refresh_token
    client_id = settings.google_client_id
    client_secret = settings.google_client_secret
    token_key = settings.token_encryption_key
    authorized_email = settings.google_authorized_email or "default"

    # ── Prefer DB-backed tokens when configured ───────────────────────────────
    client = _get_supabase_client(settings)
    if client and token_key:
        try:
            res = await asyncio.to_thread(
                lambda: (
                    client.table("google_oauth_tokens")
                    .select("*")
                    .eq("authorized_email", authorized_email)
                    .limit(1)
                    .execute()
                )
            )
            row = (res.data or [None])[0]
            if row:
                encrypted_refresh = row.get("encrypted_refresh_token")
                encrypted_access = row.get("encrypted_access_token")
                expires_at = row.get("access_token_expires_at")

                # Use cached access token if valid for >60s.
                if encrypted_access and expires_at:
                    try:
                        expiry_dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                        if (expiry_dt - _now_utc()).total_seconds() > 60:
                            return decrypt_token(str(encrypted_access), token_key)
                    except Exception:
                        pass

                # Refresh using stored refresh token.
                if encrypted_refresh and client_id and client_secret:
                    try:
                        rt = decrypt_token(str(encrypted_refresh), token_key)
                        creds = Credentials(
                            token=None,
                            refresh_token=rt,
                            token_uri=_GOOGLE_TOKEN_URI,
                            client_id=client_id,
                            client_secret=client_secret,
                        )
                        creds.refresh(Request())
                        if creds.token:
                            await asyncio.to_thread(
                                lambda: (
                                    client.table("google_oauth_tokens")
                                    .upsert(
                                        {
                                            "authorized_email": authorized_email,
                                            "encrypted_refresh_token": str(encrypted_refresh),
                                            "encrypted_access_token": encrypt_token(creds.token, token_key),
                                            "access_token_expires_at": creds.expiry.isoformat() if creds.expiry else None,
                                            "updated_at": _now_utc().isoformat(),
                                        },
                                        on_conflict="authorized_email",
                                    )
                                    .execute()
                                )
                            )
                            return creds.token
                    except Exception as exc:
                        logger.warning(
                            "google_oauth_db_refresh_failed",
                            extra={"authorized_email": authorized_email, "error": str(exc)},
                        )
        except Exception as exc:
            logger.warning("google_oauth_db_read_failed", extra={"error": str(exc)})

    if not refresh_token:
        logger.warning(
            "google_oauth_token_unavailable",
            extra={
                "reason": "GOOGLE_OAUTH_REFRESH_TOKEN not set",
                "phase_hint": "Set GOOGLE_OAUTH_REFRESH_TOKEN in .env for Phase 7 local dev",
            },
        )
        return None

    if not client_id or not client_secret:
        logger.warning(
            "google_oauth_token_unavailable",
            extra={
                "reason": "GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not set",
                "phase_hint": "Set these in .env to exchange the refresh token",
            },
        )
        return None

    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=_GOOGLE_TOKEN_URI,
            client_id=client_id,
            client_secret=client_secret,
        )
        # Perform the token refresh synchronously (google-auth is sync).
        creds.refresh(Request())

        logger.debug(
            "google_oauth_token_refreshed",
            extra={
                "expiry": creds.expiry.isoformat() if creds.expiry else "unknown",
            },
        )
        return creds.token

    except Exception as exc:
        logger.error(
            "google_oauth_token_refresh_failed",
            extra={"error": str(exc)},
        )
        return None
