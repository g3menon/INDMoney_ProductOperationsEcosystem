"""Booking repository — Phase 5.

InMemoryBookingRepository  — default for test/eval environments.
SupabaseBookingRepository  — used when BOOKING_STORAGE_MODE=supabase.

Architecture: repositories are the ONLY path to Supabase (Rules G2, §10.3).
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from app.core.config import Settings
from app.schemas.booking import BookingDetail, BookingStatus

logger = logging.getLogger(__name__)


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
    """Thread-safe in-memory repository for tests and eval runs.

    Does not write booking_events — event auditing is a production/Supabase concern.
    """

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
            # Register idempotency key so duplicate submissions are detected (G9, D6).
            if detail.idempotency_key:
                self._by_idempotency[detail.idempotency_key] = detail.booking_id
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


class SupabaseBookingRepository:
    """Supabase-backed booking repository.

    Tables (phase5_schema.sql):
      bookings:       booking_id (PK), idempotency_key (unique nullable),
                      session_id, customer_name, customer_email, issue_summary,
                      preferred_date, preferred_time, status, cancellation_reason,
                      display_timezone, created_at, updated_at
      booking_events: event_id (PK), booking_id (FK), from_status, to_status,
                      reason, actor, created_at
    """

    def __init__(self, settings: Settings) -> None:
        from supabase import Client, create_client

        self._client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )

    # ── Private helpers ──────────────────────────────────────────────

    def _row_to_detail(self, row: dict) -> BookingDetail:
        return BookingDetail(
            booking_id=row["booking_id"],
            session_id=row.get("session_id"),
            idempotency_key=row.get("idempotency_key"),
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

    def _log_event(
        self,
        booking_id: str,
        from_status: BookingStatus | None,
        to_status: BookingStatus,
        reason: str | None = None,
        actor: str = "system",
    ) -> None:
        """Write a booking_events audit row for a state transition (Rules O2, W9).

        Failures are logged but do NOT propagate — audit is non-blocking.
        """
        try:
            row = {
                "event_id": f"BE-{uuid4().hex[:12].upper()}",
                "booking_id": booking_id,
                "from_status": from_status.value if from_status else None,
                "to_status": to_status.value,
                "reason": reason,
                "actor": actor,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._client.table("booking_events").insert(row).execute()
        except Exception as exc:
            logger.warning(
                "booking_event_log_failed",
                extra={"booking_id": booking_id, "to_status": to_status.value, "error": str(exc)},
            )

    # ── Protocol methods ─────────────────────────────────────────────

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
        """Insert booking row and write the initial booking_events audit entry."""
        row = {
            "booking_id": detail.booking_id,
            "session_id": detail.session_id,
            "idempotency_key": detail.idempotency_key,  # stored for DB-level dedup (G9)
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

        # Audit: record the initial state transition (Rules O2, W9).
        self._log_event(
            booking_id=detail.booking_id,
            from_status=None,
            to_status=detail.status,
            reason="booking_created",
        )

        return detail

    async def update_status(
        self,
        booking_id: str,
        new_status: BookingStatus,
        updated_at: datetime,
        cancellation_reason: str | None = None,
    ) -> BookingDetail:
        """Update booking status and write a booking_events audit entry."""
        # Fetch current status for the audit event (from_status).
        current = await self.get_by_id(booking_id)
        from_status = current.status if current else None

        patch: dict = {"status": new_status.value, "updated_at": updated_at.isoformat()}
        if cancellation_reason is not None:
            patch["cancellation_reason"] = cancellation_reason

        self._client.table("bookings").update(patch).eq("booking_id", booking_id).execute()

        # Audit: record the state transition (Rules O2, W9).
        self._log_event(
            booking_id=booking_id,
            from_status=from_status,
            to_status=new_status,
            reason=cancellation_reason,
        )

        updated = await self.get_by_id(booking_id)
        if updated is None:
            raise KeyError(f"booking {booking_id!r} not found after update")
        return updated


_MEM_BOOKING: InMemoryBookingRepository | None = None


def get_booking_repository(settings: Settings) -> BookingRepository:
    """Return the appropriate booking repository based on BOOKING_STORAGE_MODE.

    - BOOKING_STORAGE_MODE=memory (or unset) → InMemoryBookingRepository (default)
    - APP_ENV=test or eval                   → InMemoryBookingRepository (forced)
    - BOOKING_STORAGE_MODE=supabase          → SupabaseBookingRepository

    Follows the same pattern as get_chat_repository() in chat_repository.py.
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

    # Unknown mode — fall back to in-memory (same as chat_repository pattern).
    if _MEM_BOOKING is None:
        _MEM_BOOKING = InMemoryBookingRepository()
    return _MEM_BOOKING
