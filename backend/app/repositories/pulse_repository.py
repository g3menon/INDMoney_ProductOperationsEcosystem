"""Pulse repository (Phase 2).

Phase 2 uses an in-memory repository for tests/evals and Supabase for real runs.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from supabase import Client, create_client

from app.core.config import Settings
from app.schemas.pulse import NormalizedReview, RawReview, WeeklyPulse


class PulseRepository(Protocol):
    async def persist_raw_reviews(self, rows: list[RawReview]) -> int: ...

    async def persist_normalized_reviews(self, rows: list[NormalizedReview]) -> int: ...

    async def create_weekly_pulse(self, pulse: WeeklyPulse) -> WeeklyPulse: ...

    async def get_current_pulse(self) -> WeeklyPulse | None: ...

    async def get_pulse_history(self, limit: int = 20) -> list[WeeklyPulse]: ...

    async def get_recent_normalized_reviews(self, lookback_weeks: int, limit: int = 500) -> list[NormalizedReview]: ...


@dataclass
class InMemoryPulseRepository:
    raw: list[RawReview]
    normalized: list[NormalizedReview]
    pulses: list[WeeklyPulse]

    def __init__(self) -> None:
        self.raw = []
        self.normalized = []
        self.pulses = []

    async def persist_raw_reviews(self, rows: list[RawReview]) -> int:
        self.raw.extend(rows)
        return len(rows)

    async def persist_normalized_reviews(self, rows: list[NormalizedReview]) -> int:
        self.normalized.extend(rows)
        return len(rows)

    async def create_weekly_pulse(self, pulse: WeeklyPulse) -> WeeklyPulse:
        self.pulses.insert(0, pulse)
        return pulse

    async def get_current_pulse(self) -> WeeklyPulse | None:
        return self.pulses[0] if self.pulses else None

    async def get_pulse_history(self, limit: int = 20) -> list[WeeklyPulse]:
        return list(self.pulses[:limit])

    async def get_recent_normalized_reviews(self, lookback_weeks: int, limit: int = 500) -> list[NormalizedReview]:
        # In memory mode: return latest normalized (already ordered by append time).
        return list(self.normalized[-limit:])


class SupabasePulseRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    async def persist_raw_reviews(self, rows: list[RawReview]) -> int:
        if not rows:
            return 0
        payload = [r.model_dump() for r in rows]
        res = await asyncio.to_thread(lambda: self._client.table("reviews_raw").insert(payload).execute())
        return len(res.data or payload)

    async def persist_normalized_reviews(self, rows: list[NormalizedReview]) -> int:
        if not rows:
            return 0
        payload = [r.model_dump() for r in rows]
        res = await asyncio.to_thread(
            lambda: self._client.table("reviews_normalized").upsert(payload, on_conflict="review_id").execute()
        )
        return len(res.data or payload)

    async def create_weekly_pulse(self, pulse: WeeklyPulse) -> WeeklyPulse:
        payload = pulse.model_dump()
        await asyncio.to_thread(lambda: self._client.table("weekly_pulses").insert(payload).execute())
        return pulse

    async def get_current_pulse(self) -> WeeklyPulse | None:
        res = await asyncio.to_thread(
            lambda: self._client.table("weekly_pulses").select("*").order("created_at", desc=True).limit(1).execute()
        )
        if not res.data:
            return None
        return WeeklyPulse.model_validate(res.data[0])

    async def get_pulse_history(self, limit: int = 20) -> list[WeeklyPulse]:
        res = await asyncio.to_thread(
            lambda: self._client.table("weekly_pulses").select("*").order("created_at", desc=True).limit(limit).execute()
        )
        return [WeeklyPulse.model_validate(r) for r in (res.data or [])]

    async def get_recent_normalized_reviews(self, lookback_weeks: int, limit: int = 500) -> list[NormalizedReview]:
        # Prefer normalized_at filter (UTC).
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(weeks=lookback_weeks)).isoformat()
        def _run() -> Any:
            return (
                self._client.table("reviews_normalized")
                .select("*")
                .gte("normalized_at", cutoff_iso)
                .order("normalized_at", desc=True)
                .limit(limit)
                .execute()
            )

        res = await asyncio.to_thread(_run)
        return [NormalizedReview.model_validate(r) for r in (res.data or [])]


_MEM_REPO: InMemoryPulseRepository | None = None


def get_pulse_repository(settings: Settings) -> PulseRepository:
    global _MEM_REPO
    if settings.app_env in ("test", "eval") or os.getenv("PULSE_STORAGE_MODE", "").lower() == "memory":
        if _MEM_REPO is None:
            _MEM_REPO = InMemoryPulseRepository()
        return _MEM_REPO
    return SupabasePulseRepository(settings)
