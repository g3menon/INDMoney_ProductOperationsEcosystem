"""`GET /api/v1/health` — liveness and safe config snapshot."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.dependencies import CorrelationIdDep
from app.integrations.supabase.client import check_supabase_connectivity
from app.rag.retrieve import get_rag_index
from app.schemas.common import APIEnvelope

router = APIRouter()


@router.get("/health", response_model=APIEnvelope[dict[str, Any]])
async def health(correlation_id: CorrelationIdDep) -> APIEnvelope[dict[str, Any]]:
    settings = get_settings()
    ok, supa_msg = await check_supabase_connectivity(settings)
    rag_index = get_rag_index()
    rag_total_chunks = rag_index.total_chunks if rag_index is not None else 0
    rag_chunks_with_embedding = rag_index.chunks_with_embedding if rag_index is not None else 0
    data = {
        "status": "ok" if ok else "degraded",
        "correlation_id": correlation_id,
        "supabase": {"reachable": ok, "detail": supa_msg if not ok else "ok"},
        "rag_index_available": rag_index is not None,
        "rag_total_chunks": rag_total_chunks,
        "rag_chunks_with_embedding": rag_chunks_with_embedding,
        "retrieval_ready": bool(
            rag_index is not None
            and rag_index.bm25_available
            and rag_chunks_with_embedding > 0
        ),
        "settings": settings.safe_public_dict(),
    }
    return APIEnvelope(success=True, message="health", data=data)
