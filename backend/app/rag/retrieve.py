"""RAG retrieval orchestrator: BM25 + embeddings → RRF fusion → optional rerank.

The RAGIndex is loaded once at backend startup from the JSON chunk index file
(built by scripts/rebuild_index.py). A module-level singleton is maintained so
all request handlers share the same in-memory index (Rules L8).

Failure modes (Rules G7):
- Index file missing → RAGIndex is None → caller falls back to Phase 3 skeleton.
- Gemini key absent → embedding search skipped → BM25-only results.
- BM25 returns no hits → empty list → answer.py generates safe fallback.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.rag.bm25 import BM25Index
from app.rag.embeddings import EmbeddingIndex
from app.rag.fusion import reciprocal_rank_fusion
from app.rag.rerank import rerank
from app.schemas.rag import DocumentChunk, ScoredChunk

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

_DEFAULT_INDEX_PATH = str(
    Path(__file__).parent / "index" / "chunks.json"
)


@dataclass(frozen=True)
class RetrievalResult:
    chunks: list[ScoredChunk]
    bm25_hits: int = 0
    embedding_hits: int = 0
    fused_hits: int = 0
    retrieval_mode: str = "none"


class RAGIndex:
    """In-memory hybrid retrieval index over DocumentChunk objects."""

    def __init__(self, chunks: list[DocumentChunk], index_path: str = _DEFAULT_INDEX_PATH) -> None:
        self._chunks = chunks
        self._index_path = index_path
        self._bm25 = BM25Index()
        self._bm25.build(chunks)
        self._embeddings = EmbeddingIndex()
        self._embeddings.build(chunks)
        logger.info(
            "rag_index_loaded",
            extra={"total_chunks": len(chunks), "path": index_path},
        )

    @property
    def total_chunks(self) -> int:
        return len(self._chunks)

    @property
    def chunks_with_embedding(self) -> int:
        return sum(1 for chunk in self._chunks if chunk.embedding is not None)

    @property
    def bm25_available(self) -> bool:
        return bool(getattr(self._bm25, "_chunks", None)) and getattr(self._bm25, "_bm25", None) is not None

    @property
    def embeddings_available(self) -> bool:
        return self.chunks_with_embedding > 0

    @classmethod
    def load(cls, index_path: str) -> "RAGIndex":
        """Load index from a JSON file of serialized DocumentChunk objects."""
        path = Path(index_path)
        if not path.exists():
            raise FileNotFoundError(f"RAG index not found: {index_path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        chunks = [DocumentChunk.model_validate(r) for r in raw]
        return cls(chunks=chunks, index_path=index_path)

    @classmethod
    def load_default(cls) -> "RAGIndex | None":
        """Try to load from the default index path; return None if missing."""
        try:
            return cls.load(_DEFAULT_INDEX_PATH)
        except FileNotFoundError:
            logger.warning(
                "rag_index_missing",
                extra={"path": _DEFAULT_INDEX_PATH, "hint": "run scripts/rebuild_index.py"},
            )
            return None
        except Exception as exc:
            logger.error("rag_index_load_error", extra={"error": str(exc)})
            return None

    async def search(
        self,
        query: str,
        settings: "Settings",
        top_k: int = 5,
        use_rerank: bool = False,
    ) -> list[ScoredChunk]:
        """Hybrid BM25 + embedding retrieval → RRF fusion → optional LLM rerank."""
        result = await self.search_with_metadata(
            query=query,
            settings=settings,
            top_k=top_k,
            use_rerank=use_rerank,
        )
        return result.chunks

    async def search_with_metadata(
        self,
        query: str,
        settings: "Settings",
        top_k: int = 5,
        use_rerank: bool = False,
    ) -> RetrievalResult:
        """Hybrid BM25 + embedding retrieval with observable retrieval metadata."""
        t0 = time.monotonic()

        bm25_results = self._bm25.search(query, top_k=top_k * 2)
        emb_results = await self._embeddings.search(query, settings, top_k=top_k * 2)

        ranked_lists: list[list[ScoredChunk]] = []
        if bm25_results:
            ranked_lists.append(bm25_results)
        if emb_results:
            ranked_lists.append(emb_results)

        if not ranked_lists:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                "rag_retrieve_done",
                extra={
                    "query_len": len(query),
                    "bm25_hits": len(bm25_results),
                    "emb_hits": len(emb_results),
                    "fused": 0,
                    "returned": 0,
                    "retrieval_mode": "none",
                    "elapsed_ms": elapsed_ms,
                },
            )
            return RetrievalResult(
                chunks=[],
                bm25_hits=len(bm25_results),
                embedding_hits=len(emb_results),
                fused_hits=0,
                retrieval_mode="none",
            )

        fused = reciprocal_rank_fusion(ranked_lists)[:top_k * 2]

        if use_rerank and len(fused) > top_k:
            final = await rerank(query, fused, settings, top_k=top_k)
        else:
            final = fused[:top_k]

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "rag_retrieve_done",
            extra={
                "query_len": len(query),
                "bm25_hits": len(bm25_results),
                "emb_hits": len(emb_results),
                "fused": len(fused),
                "returned": len(final),
                "retrieval_mode": "hybrid" if emb_results else "bm25_only",
                "elapsed_ms": elapsed_ms,
            },
        )
        return RetrievalResult(
            chunks=final,
            bm25_hits=len(bm25_results),
            embedding_hits=len(emb_results),
            fused_hits=len(fused),
            retrieval_mode="hybrid" if emb_results else "bm25_only",
        )


# ---------------------------------------------------------------------------
# Module-level singleton (loaded at backend startup in main.py)
# ---------------------------------------------------------------------------

_rag_index: RAGIndex | None = None


def get_rag_index() -> RAGIndex | None:
    return _rag_index


def set_rag_index(index: RAGIndex | None) -> None:
    global _rag_index
    _rag_index = index


async def load_rag_index_from_default() -> None:
    """Called at startup (main.py lifespan). Safe to call even if index is absent."""
    idx = RAGIndex.load_default()
    set_rag_index(idx)
