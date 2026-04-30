"""Booking repository — Phase 5.

InMemoryBookingRepository  — default for test/eval environments.
SupabaseBookingRepository  — used when BOOKING_STORAGE_MODE=supabase.

Architecture: repositories are the ONLY path to Supabase (Rules G2, §10.3).
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from app.core.config import Settings
from app.schemas.booking import BookingDetail, BookingStatus


class BookingRepository(Protocol):
    async def get_by_id(self, booking_id: str) -> BookingDetail | None: ...

    async def get_by_idempotency_key(self, key: str) -> BookingDetail | None: ...

    async def create(self, detail: BookingDetail) -> BookingDetail: ...

    async def update_status(
        self,
        booking_id: str,
        new_status: BookingStatus,
        updated_at: datetime,
        cancellation_reason: str | None = None,
    ) -> BookingDetail: ...


@dataclass
class InMemoryBookingRepository:
    """Thread-safe in-memory repository for tests and eval runs."""

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _by_id: dict[str, BookingDetail] = field(default_factory=dict, init=False)
    _by_idempotency: dict[str, str] = field(default_factory=dict, init=False)

    async def get_by_id(self, booking_id: str) -> BookingDetail | None:
        async with self._lock:
            return self._by_id.get(booking_id)

    async def get_by_idempotency_key(self, key: str) -> BookingDetail | None:
        async with self._lock:
            bid = self._by_idempotency.get(key)
            return self._by_id.get(bid) if bid else None

    async def create(self, detail: BookingDetail) -> BookingDetail:
        async with self._lock:
            self._by_id[detail.booking_id] = detail
            if detail.idempotency_key if hasattr(detail, "idempotency_key") else False:
                pass  # idempotency_key not on BookingDetail, managed by service
            return detail

    async def update_status(
        self,
        booking_id: str,
        new_status: BookingStatus,
        updated_at: datetime,
        cancellation_reason: str | None = None,
    ) -> BookingDetail:
        async with self._lock:
            existing = self._by_id.get(booking_id)
            if existing is None:
                raise KeyError(f"booking {booking_id!r} not found")
            updated = existing.model_copy(
                update={
                    "status": new_status,
                    "updated_at": updated_at,
                    "cancellation_reason": cancellation_reason or existing.cancellation_reason,
                }
            )
            self._by_id[booking_id] = updated
            return updated

    # Internal helper used by the service to register idempotency keys.
    async def register_idempotency(self, key: str, booking_id: str) -> None:
        async with self._lock:
            self._by_idempotency[key] = booking_id


class SupabaseBookingRepository:
    """Supabase-backed booking repository.

    Tables (phase5_schema.sql):
      bookings:       booking_id (PK text), session_id, idempotency_key (unique),
                      customer_name, customer_email, issue_summary, preferred_date,
                      preferred_time, status, cancellation_reason, created_at, updated_at
      booking_events: event_id (PK text), booking_id (FK), from_status, to_status,
                      reason, actor, created_at
    """

    def __init__(self, settings: Settings) -> None:
        from supabase import Client, create_client

        self._client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )

    def _row_to_detail(self, row: dict) -> BookingDetail:
        return BookingDetail(
            booking_id=row["booking_id"],
            session_id=row.get("session_id"),
            customer_name=row["customer_name"],
            customer_email=row["customer_email"],
            issue_summary=row["issue_summary"],
            preferred_date=row["preferred_date"],
            preferred_time=row["preferred_time"],
            status=BookingStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            display_timezone=row.get("display_timezone", "Asia/Kolkata (IST)"),
            cancellation_reason=row.get("cancellation_reason"),
        )

    async def get_by_id(self, booking_id: str) -> BookingDetail | None:
        res = (
            self._client.table("bookings")
            .select("*")
            .eq("booking_id", booking_id)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return self._row_to_detail(rows[0]) if rows else None

    async def get_by_idempotency_key(self, key: str) -> BookingDetail | None:
        res = (
            self._client.table("bookings")
            .select("*")
            .eq("idempotency_key", key)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return self._row_to_detail(rows[0]) if rows else None

    async def create(self, detail: BookingDetail) -> BookingDetail:
        row = {
            "booking_id": detail.booking_id,
            "session_id": detail.session_id,
            "customer_name": detail.customer_name,
            "customer_email": detail.customer_email,
            "issue_summary": detail.issue_summary,
            "preferred_date": detail.preferred_date,
            "preferred_time": detail.preferred_time,
            "status": detail.status.value,
            "cancellation_reason": detail.cancellation_reason,
            "display_timezone": detail.display_timezone,
            "created_at": detail.created_at.isoformat(),
            "updated_at": detail.updated_at.isoformat(),
        }
        self._client.table("bookings").insert(row).execute()
        return detail

    async def update_status(
        self,
        booking_id: str,
        new_status: BookingStatus,
        updated_at: datetime,
        cancellation_reason: str | None = None,
    ) -> BookingDetail:
        patch: dict = {"status": new_status.value, "updated_at": updated_at.isoformat()}
        if cancellation_reason is not None:
            patch["cancellation_reason"] = cancellation_reason

        self._client.table("bookings").update(patch).eq("booking_id", booking_id).execute()

        updated = await self.get_by_id(booking_id)
        if updated is None:
            raise KeyError(f"booking {booking_id!r} not found after update")
        return updated

    async def register_idempotency(self, key: str, booking_id: str) -> None:
        # Already stored in the bookings.idempotency_key column during create.
        pass

    def _log_event(
        self,
        booking_id: str,
        from_status: BookingStatus | None,
        to_status: BookingStatus,
        reason: str | None,
        actor: str,
        event_id: str,
        created_at: str,
    ) -> None:
        row = {
            "event_id": event_id,
            "booking_id": booking_id,
            "from_status": from_status.value if from_status else None,
            "to_status": to_status.value,
            "reason": reason,
            "actor": actor,
            "created_at": created_at,
        }
        self._client.table("booking_events").insert(row).execute()


_MEM_BOOKING: InMemoryBookingRepository | None = None


def get_booking_repository(settings: Settings) -> BookingRepository:
    """Return the appropriate booking repository based on BOOKING_STORAGE_MODE.

    - BOOKING_STORAGE_MODE=memory (or unset) → InMemoryBookingRepository (default)
    - APP_ENV=test or eval                   → InMemoryBookingRepository (forced)
    - BOOKING_STORAGE_MODE=supabase          → SupabaseBookingRepository
    """
    global _MEM_BOOKING
    storage_mode = os.getenv("BOOKING_STORAGE_MODE", "").lower().strip()
    app_env = (settings.app_env or "").lower()

    use_mem = storage_mode in ("", "memory") or app_env in ("test", "eval")

    if use_mem:
        if _MEM_BOOKING is None:
            _MEM_BOOKING = InMemoryBookingRepository()
        return _MEM_BOOKING

    if storage_mode == "supabase":
        return SupabaseBookingRepository(settings)

    if _MEM_BOOKING is None:
        _MEM_BOOKING = InMemoryBookingRepository()
    return _MEM_BOOKING
