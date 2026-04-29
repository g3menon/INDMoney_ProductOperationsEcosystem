"""Phase 4: MF source document and structured metrics repository.

Follows the Protocol + InMemory + Supabase pattern used by pulse_repository
and chat_repository.

Supabase write path is controlled by the INGEST_SKIP_SUPABASE env flag:
  unset / "false"  → Supabase upserts enabled
  "1" / "true"     → skip Supabase writes; local JSON files are still produced

Both upserts are individually wrapped in try/except so a Supabase failure
never crashes the ingestion script; it only logs a WARNING and continues.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

from app.schemas.rag import MFFundMetrics, SourceDocument

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

_SKIP_SUPABASE = os.getenv("INGEST_SKIP_SUPABASE", "").lower() in (
    "1", "true", "yes"
)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class MFRepository(Protocol):
    async def upsert_source_document(self, doc: SourceDocument) -> None: ...

    async def upsert_fund_metrics(self, metrics: MFFundMetrics) -> None: ...

    async def get_all_metrics(self) -> list[MFFundMetrics]: ...


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------


@dataclass
class InMemoryMFRepository:
    _docs: dict[str, SourceDocument] = field(default_factory=dict)
    _metrics: dict[str, MFFundMetrics] = field(default_factory=dict)

    def __init__(self) -> None:
        self._docs = {}
        self._metrics = {}

    async def upsert_source_document(self, doc: SourceDocument) -> None:
        self._docs[doc.doc_id] = doc

    async def upsert_fund_metrics(self, metrics: MFFundMetrics) -> None:
        self._metrics[metrics.doc_id] = metrics

    async def get_all_metrics(self) -> list[MFFundMetrics]:
        return list(self._metrics.values())


# ---------------------------------------------------------------------------
# Supabase implementation
# ---------------------------------------------------------------------------


class SupabaseMFRepository:
    """Upserts source_documents and mf_fund_metrics via supabase-py."""

    def __init__(self, settings: "Settings") -> None:
        from supabase import create_client  # type: ignore

        self._client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )

    async def upsert_source_document(self, doc: SourceDocument) -> None:
        import asyncio

        content_hash = hashlib.sha256(doc.content.encode()).hexdigest()
        row = {
            "doc_id": doc.doc_id,
            "url": doc.url,
            "title": doc.title,
            "doc_type": doc.doc_type,
            "last_checked": doc.last_checked,
            "content_hash": content_hash,
            "raw_char_count": len(doc.content),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
        }
        try:
            await asyncio.to_thread(
                lambda: self._client.table("source_documents")
                .upsert(row, on_conflict="doc_id")
                .execute()
            )
            logger.info(
                "supabase_mf_doc_upsert_ok", extra={"doc_id": doc.doc_id}
            )
        except Exception as exc:
            logger.warning(
                "supabase_mf_doc_upsert_failed",
                extra={"doc_id": doc.doc_id, "error": str(exc)[:120]},
            )

    async def upsert_fund_metrics(self, metrics: MFFundMetrics) -> None:
        import asyncio

        row = {
            "doc_id": metrics.doc_id,
            "fund_name": metrics.fund_name,
            "amc": metrics.amc,
            "category": metrics.category,
            "sub_category": metrics.sub_category,
            "plan": metrics.plan,
            "option": metrics.option,
            "nav": float(metrics.nav) if metrics.nav is not None else None,
            "nav_date": metrics.nav_date,
            "aum_cr": float(metrics.aum_cr) if metrics.aum_cr is not None else None,
            "expense_ratio_pct": (
                float(metrics.expense_ratio_pct)
                if metrics.expense_ratio_pct is not None
                else None
            ),
            "exit_load_pct": (
                float(metrics.exit_load_pct)
                if metrics.exit_load_pct is not None
                else None
            ),
            "exit_load_window_days": metrics.exit_load_window_days,
            "exit_load_description": metrics.exit_load_description,
            "risk_level": metrics.risk_level,
            "rating": metrics.rating,
            "benchmark": metrics.benchmark,
            "min_sip_amount": (
                float(metrics.min_sip_amount)
                if metrics.min_sip_amount is not None
                else None
            ),
            "min_lumpsum_amount": (
                float(metrics.min_lumpsum_amount)
                if metrics.min_lumpsum_amount is not None
                else None
            ),
            "returns": metrics.returns.model_dump() if metrics.returns else None,
            "top_holdings": [h.model_dump() for h in metrics.top_holdings],
            "sector_allocation": [s.model_dump() for s in metrics.sector_allocation],
            "asset_allocation": metrics.asset_allocation,
            "fund_objective": metrics.fund_objective,
            "scraped_at": metrics.scraped_at,
            "last_checked": metrics.last_checked,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await asyncio.to_thread(
                lambda: self._client.table("mf_fund_metrics")
                .upsert(row, on_conflict="doc_id")
                .execute()
            )
            logger.info(
                "supabase_mf_metrics_upsert_ok",
                extra={"doc_id": metrics.doc_id},
            )
        except Exception as exc:
            logger.warning(
                "supabase_mf_metrics_upsert_failed",
                extra={"doc_id": metrics.doc_id, "error": str(exc)[:120]},
            )

    async def get_all_metrics(self) -> list[MFFundMetrics]:
        import asyncio

        try:
            result = await asyncio.to_thread(
                lambda: self._client.table("mf_fund_metrics").select("*").execute()
            )
            return [MFFundMetrics.model_validate(r) for r in (result.data or [])]
        except Exception as exc:
            logger.warning(
                "supabase_mf_metrics_fetch_failed",
                extra={"error": str(exc)[:120]},
            )
            return []


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_mf_repository(settings: "Settings") -> "MFRepository":
    """Return the appropriate MF repository based on env configuration."""
    if _SKIP_SUPABASE:
        logger.info(
            "mf_repository_in_memory",
            extra={"reason": "INGEST_SKIP_SUPABASE is set"},
        )
        return InMemoryMFRepository()
    try:
        return SupabaseMFRepository(settings)
    except Exception as exc:
        logger.warning(
            "mf_repository_supabase_init_failed_using_in_memory",
            extra={"error": str(exc)[:80]},
        )
        return InMemoryMFRepository()
