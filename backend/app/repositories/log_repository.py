"""Integration log repository — Phase 7.

Persists external action outcomes for operational debugging and idempotency audit.
All methods degrade gracefully when Supabase isn't configured.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from supabase import Client, create_client

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class SupabaseLogRepository:
    _client: Client

    @classmethod
    def from_settings(cls, settings: Settings) -> "SupabaseLogRepository | None":
        if not settings.supabase_url or not settings.supabase_service_role_key:
            return None
        return cls(create_client(settings.supabase_url, settings.supabase_service_role_key))

    async def insert(self, table: str, payload: dict[str, Any]) -> None:
        await asyncio.to_thread(lambda: self._client.table(table).insert(payload).execute())


async def log_pulse_send(
    *,
    settings: Settings,
    pulse_id: str | None,
    email: str,
    status: str,
    provider_message_id: str | None = None,
    error: str | None = None,
) -> None:
    repo = SupabaseLogRepository.from_settings(settings)
    if repo is None:
        return
    try:
        await repo.insert(
            "pulse_send_logs",
            {
                "pulse_id": pulse_id,
                "email": email,
                "status": status,
                "provider_message_id": provider_message_id,
                "error": error,
            },
        )
    except Exception as exc:
        logger.warning("log_pulse_send_failed", extra={"error": str(exc)})


async def log_email_action(
    *,
    settings: Settings,
    correlation_id: str | None,
    idempotency_key: str | None,
    action_type: str,
    booking_id: str | None,
    pulse_id: str | None,
    to_email: str,
    from_email: str | None,
    subject: str,
    status: str,
    provider_message_id: str | None = None,
    error: str | None = None,
) -> None:
    repo = SupabaseLogRepository.from_settings(settings)
    if repo is None:
        return
    try:
        await repo.insert(
            "email_actions",
            {
                "correlation_id": correlation_id,
                "idempotency_key": idempotency_key,
                "action_type": action_type,
                "booking_id": booking_id,
                "pulse_id": pulse_id,
                "to_email": to_email,
                "from_email": from_email,
                "subject": subject,
                "status": status,
                "provider_message_id": provider_message_id,
                "error": error,
            },
        )
    except Exception as exc:
        logger.warning("log_email_action_failed", extra={"error": str(exc)})

