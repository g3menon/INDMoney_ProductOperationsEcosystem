"""Token repository — Phase 7.

Provides a Google OAuth access token for use by integration services.

Phase 7 strategy (env-var fallback only):
- Read GOOGLE_OAUTH_REFRESH_TOKEN from Settings.
- If present, exchange it for a fresh access token using GOOGLE_CLIENT_ID +
  GOOGLE_CLIENT_SECRET via google-auth's Request.refresh().
- Return the live access token string.

# TODO Phase 8: replace env var fallback with DB read from google_oauth_tokens table.
# The google_oauth_tokens table will be created in Phase 8 (infra/supabase/).
# get_google_oauth_token() should:
#   1. SELECT the row for google_authorized_email from google_oauth_tokens.
#   2. If expires_at is in the future, decrypt and return the stored access_token.
#   3. If expired, refresh using the stored (encrypted) refresh_token, persist
#      the updated access_token + new expires_at, and return the fresh value.
#   4. Fall back to the env var path only if no DB row exists.

Rules satisfied:
  I2  — OAuth credentials stay server-side only.
  D7  — tokens never persisted in plaintext (Phase 8 will encrypt at rest).
  G7  — graceful failure: return None when unconfigured; callers skip with warning.
  G5  — no secrets in code; all values come from Settings.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


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
