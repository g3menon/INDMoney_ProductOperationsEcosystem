"""Pulse subscription repository (Phase 2)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from supabase import Client, create_client

from app.core.config import Settings


class SubscriptionRepository(Protocol):
    async def subscribe(self, email: str) -> tuple[str, str]: ...

    async def unsubscribe(self, email: str) -> tuple[str, str]: ...

    async def count_active(self) -> int: ...

    async def list_active(self) -> list[str]: ...


@dataclass
class InMemorySubscriptionRepository:
    active: set[str]

    def __init__(self) -> None:
        self.active = set()

    async def subscribe(self, email: str) -> tuple[str, str]:
        self.active.add(email.lower())
        return email.lower(), "subscribed"

    async def unsubscribe(self, email: str) -> tuple[str, str]:
        self.active.discard(email.lower())
        return email.lower(), "unsubscribed"

    async def count_active(self) -> int:
        return len(self.active)

    async def list_active(self) -> list[str]:
        return sorted(self.active)


class SupabaseSubscriptionRepository:
    def __init__(self, settings: Settings) -> None:
        self._client: Client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    async def subscribe(self, email: str) -> tuple[str, str]:
        payload = {"email": email.lower(), "active": True, "updated_at": datetime.utcnow().isoformat()}
        self._client.table("pulse_subscriptions").upsert(payload, on_conflict="email").execute()
        return email.lower(), "subscribed"

    async def unsubscribe(self, email: str) -> tuple[str, str]:
        payload = {"email": email.lower(), "active": False, "updated_at": datetime.utcnow().isoformat()}
        self._client.table("pulse_subscriptions").upsert(payload, on_conflict="email").execute()
        return email.lower(), "unsubscribed"

    async def count_active(self) -> int:
        res = self._client.table("pulse_subscriptions").select("email", count="exact").eq("active", True).execute()
        return int(getattr(res, "count", 0) or 0)

    async def list_active(self) -> list[str]:
        res = (
            self._client.table("pulse_subscriptions")
            .select("email")
            .eq("active", True)
            .order("updated_at", desc=True)
            .limit(1000)
            .execute()
        )
        rows = res.data or []
        return [str(r["email"]).lower() for r in rows if r.get("email")]


_MEM_SUBS: InMemorySubscriptionRepository | None = None


def get_subscription_repository(settings: Settings) -> SubscriptionRepository:
    global _MEM_SUBS
    if settings.app_env in ("test", "eval") or os.getenv("PULSE_STORAGE_MODE", "").lower() == "memory":
        if _MEM_SUBS is None:
            _MEM_SUBS = InMemorySubscriptionRepository()
        return _MEM_SUBS
    return SupabaseSubscriptionRepository(settings)
