"""Dense embedding index using Gemini embedding model (Phase 4, Rules R11, P4.6).

Uses google-generativeai genai.embed_content with the text-embedding-004 model.
Degrades gracefully to BM25-only when Gemini key is absent (Rules G7, R10).
Cosine similarity is computed in-memory with numpy (or pure-Python fallback).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.schemas.rag import DocumentChunk, ScoredChunk
from app.llm.throttle import wait_for_slot

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "models/text-embedding-004"
EMBED_BATCH_SIZE = 20  # keep individual calls small (Rules I8)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity using numpy if available, else pure Python."""
    try:
        import numpy as np  # type: ignore

        va = np.array(a, dtype=float)
        vb = np.array(b, dtype=float)
        denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
        return float(np.dot(va, vb) / denom) if denom > 0 else 0.0
    except ImportError:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        return dot / (norm_a * norm_b) if (norm_a > 0 and norm_b > 0) else 0.0


def _embed_text_sync(text: str, settings: "Settings", task_type: str = "retrieval_query") -> list[float] | None:
    """Call Gemini embedding API synchronously. Returns None on failure."""
    key = settings.gemini_api_key
    if not key:
        return None
    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=key)
        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=text,
            task_type=task_type,
        )
        return list(result["embedding"])
    except Exception as exc:
        logger.warning("embedding_failed", extra={"error": str(exc)[:120]})
        return None


class EmbeddingIndex:
    """In-memory embedding index for dense retrieval."""

    def __init__(self) -> None:
        self._chunks: list[DocumentChunk] = []

    def build(self, chunks: list[DocumentChunk]) -> None:
        """Store chunks (embeddings already attached or None)."""
        self._chunks = [c for c in chunks if c.embedding is not None]
        logger.info(
            "embedding_index_built",
            extra={"chunks_with_embedding": len(self._chunks), "total_chunks": len(chunks)},
        )

    async def embed_chunks(self, chunks: list[DocumentChunk], settings: "Settings") -> list[DocumentChunk]:
        """Generate embeddings for a batch of chunks. Returns updated chunks."""
        result: list[DocumentChunk] = []
        for chunk in chunks:
            if chunk.embedding is not None:
                result.append(chunk)
                continue
            # Guardrail 3: script-level RPM throttling for Gemini embed calls.
            await wait_for_slot("gemini", settings=settings)
            vec = await asyncio.to_thread(
                _embed_text_sync, chunk.content, settings, "retrieval_document"
            )
            result.append(chunk.model_copy(update={"embedding": vec}))
        return result

    async def search(
        self,
        query: str,
        settings: "Settings",
        top_k: int = 10,
    ) -> list[ScoredChunk]:
        """Return top_k chunks by cosine similarity to the query embedding."""
        if not self._chunks:
            return []

        query_vec = await asyncio.to_thread(_embed_text_sync, query, settings, "retrieval_query")
        if query_vec is None:
            return []

        scored: list[ScoredChunk] = []
        for chunk in self._chunks:
            if chunk.embedding:
                sim = _cosine_similarity(query_vec, chunk.embedding)
                scored.append(ScoredChunk(chunk=chunk, score=sim))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]
