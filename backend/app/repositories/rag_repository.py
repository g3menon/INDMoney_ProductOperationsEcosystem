"""Supabase-backed RAG chunk repository.

The repository stores durable DocumentChunk rows in public.rag_chunks and exposes
BM25-style full-text search plus pgvector cosine retrieval.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.core.config import Settings
from app.schemas.rag import DocumentChunk, ReviewFilter, ScoredChunk

logger = logging.getLogger(__name__)


class SupabaseRAGRepository:
    """Repository for durable RAG chunks in Supabase."""

    def __init__(self, settings: Settings) -> None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise ValueError("Supabase RAG storage requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")

        from supabase import Client, create_client

        self._client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )

    async def upsert_chunk(self, chunk: DocumentChunk) -> None:
        """Insert or update one RAG chunk."""
        await asyncio.to_thread(
            lambda: self._client.table("rag_chunks")
            .upsert(_chunk_to_row(chunk), on_conflict="id")
            .execute()
        )

    async def upsert_chunks_batch(self, chunks: list[DocumentChunk]) -> None:
        """Insert or update chunks in small batches for PostgREST stability."""
        if not chunks:
            return

        batch_size = 100
        for start in range(0, len(chunks), batch_size):
            rows = [_chunk_to_row(chunk) for chunk in chunks[start : start + batch_size]]
            await asyncio.to_thread(
                lambda rows=rows: self._client.table("rag_chunks")
                .upsert(rows, on_conflict="id")
                .execute()
            )

    async def search_bm25(
        self,
        query: str,
        top_k: int,
        filter: ReviewFilter | None = None,
    ) -> list[ScoredChunk]:
        """Full-text search over content using Postgres tsvector matching."""
        q = (query or "").strip()
        if not q or top_k <= 0:
            return []

        def _with_review_filter(base: Any) -> Any:
            if filter is None:
                return base
            base = base.filter("doc_type", "eq", "playstore_review")
            if filter.min_rating is not None:
                base = base.filter("rating", "gte", filter.min_rating)
            if filter.max_rating is not None:
                base = base.filter("rating", "lte", filter.max_rating)
            if filter.date_from is not None:
                base = base.filter("review_date", "gte", filter.date_from)
            if filter.date_to is not None:
                base = base.filter("review_date", "lte", filter.date_to)
            return base

        def _search() -> Any:
            try:
                sb_query = (
                    self._client.table("rag_chunks")
                    .select("*")
                    .text_search("content", q, config="english")
                )
                return _with_review_filter(sb_query).limit(top_k).execute()
            except TypeError:
                sb_query = (
                    self._client.table("rag_chunks")
                    .select("*")
                    .text_search("content", q)
                )
                return _with_review_filter(sb_query).limit(top_k).execute()
            except AttributeError:
                sb_query = (
                    self._client.table("rag_chunks")
                    .select("*")
                    .filter("content", "fts", q)
                )
                return _with_review_filter(sb_query).limit(top_k).execute()

        try:
            res = await asyncio.to_thread(_search)
        except Exception as exc:
            logger.warning("rag_bm25_search_failed", extra={"error": str(exc)[:160]})
            return []

        rows = res.data or []
        scored: list[ScoredChunk] = []
        for idx, row in enumerate(rows):
            chunk = _row_to_chunk(row)
            score = float(max(top_k - idx, 1))
            scored.append(ScoredChunk(chunk=chunk, score=score))
        return scored

    async def search_embedding(
        self,
        query_vector: list[float],
        top_k: int,
        filter: ReviewFilter | None = None,
    ) -> list[ScoredChunk]:
        """Cosine similarity search through the match_chunks RPC."""
        if not query_vector or top_k <= 0:
            return []

        rpc_args: dict[str, Any] = {"query_embedding": query_vector, "match_count": top_k}
        if filter is not None:
            rpc_args.update(
                {
                    "filter_doc_type": "playstore_review",
                    "filter_min_rating": filter.min_rating,
                    "filter_max_rating": filter.max_rating,
                    "filter_date_from": filter.date_from,
                    "filter_date_to": filter.date_to,
                }
            )

        try:
            res = await asyncio.to_thread(
                lambda: self._client.rpc(
                    "match_chunks",
                    rpc_args,
                ).execute()
            )
        except Exception as exc:
            logger.warning("rag_embedding_search_failed", extra={"error": str(exc)[:160]})
            return []

        matches = res.data or []
        ids = [row.get("id") for row in matches if row.get("id")]
        if not ids:
            return []

        try:
            rows_res = await asyncio.to_thread(
                lambda: self._client.table("rag_chunks").select("*").in_("id", ids).execute()
            )
        except Exception as exc:
            logger.warning("rag_embedding_hydrate_failed", extra={"error": str(exc)[:160]})
            return []

        rows_by_id = {row.get("id"): row for row in (rows_res.data or [])}
        scored: list[ScoredChunk] = []
        for match in matches:
            row = rows_by_id.get(match.get("id"))
            if not row:
                continue
            scored.append(
                ScoredChunk(
                    chunk=_row_to_chunk(row),
                    score=float(match.get("similarity") or 0.0),
                )
            )
        return scored

    async def get_stats(self) -> dict[str, int]:
        """Return total chunk counts from the get_rag_stats RPC."""
        defaults = {
            "total_chunks": 0,
            "chunks_with_embedding": 0,
            "chunks_with_review_metadata": 0,
        }
        try:
            res = await asyncio.to_thread(lambda: self._client.rpc("get_rag_stats").execute())
        except Exception as exc:
            logger.warning("rag_stats_failed", extra={"error": str(exc)[:160]})
            return defaults

        rows = res.data or []
        if not rows:
            return defaults
        row = rows[0]
        return {
            "total_chunks": int(row.get("total_chunks") or 0),
            "chunks_with_embedding": int(row.get("chunks_with_embedding") or 0),
            "chunks_with_review_metadata": int(row.get("chunks_with_review_metadata") or 0),
        }


def _chunk_to_row(chunk: DocumentChunk) -> dict[str, Any]:
    return {
        "id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "content": chunk.content,
        "embedding": chunk.embedding,
        "doc_type": chunk.doc_type,
        "source_url": chunk.source_url,
        "title": chunk.title,
        "last_checked": chunk.last_checked,
        "chunk_index": chunk.chunk_index,
        "rating": chunk.rating,
        "review_date": chunk.review_date,
        "app_version": chunk.app_version,
        "found_review_helpful": chunk.found_review_helpful,
    }


def _row_to_chunk(row: dict[str, Any]) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=str(row.get("id") or ""),
        doc_id=str(row.get("doc_id") or row.get("id") or ""),
        source_url=str(row.get("source_url") or ""),
        title=str(row.get("title") or ""),
        doc_type=row.get("doc_type") or "mutual_fund_page",
        last_checked=str(row.get("last_checked") or ""),
        content=str(row.get("content") or ""),
        chunk_index=int(row.get("chunk_index") or 0),
        embedding=_parse_embedding(row.get("embedding")),
        rating=row.get("rating"),
        review_date=row.get("review_date"),
        app_version=row.get("app_version"),
        found_review_helpful=row.get("found_review_helpful"),
    )


def _parse_embedding(value: Any) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [float(v) for v in value]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [float(v) for v in parsed]
        except json.JSONDecodeError:
            pass
        if text.startswith("[") and text.endswith("]"):
            try:
                return [float(part.strip()) for part in text[1:-1].split(",") if part.strip()]
            except ValueError:
                return None
    return None
