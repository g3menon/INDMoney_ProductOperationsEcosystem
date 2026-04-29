"""BM25 sparse retrieval index for the Phase 4 RAG pipeline (Rules R11, P4.6).

Uses rank-bm25 (BM25Okapi). Falls back to keyword overlap scoring if rank-bm25
is not installed so the rest of the RAG stack stays runnable (Rules G7).
"""

from __future__ import annotations

import logging
import re

from app.schemas.rag import DocumentChunk, ScoredChunk

logger = logging.getLogger(__name__)

_TOKENIZE_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKENIZE_RE.findall(text.lower())


class BM25Index:
    """In-memory BM25 index over a list of DocumentChunk objects."""

    def __init__(self) -> None:
        self._chunks: list[DocumentChunk] = []
        self._bm25: object | None = None

    def build(self, chunks: list[DocumentChunk]) -> None:
        """Build the BM25 index from a list of DocumentChunk objects."""
        self._chunks = list(chunks)
        if not self._chunks:
            logger.warning("bm25_build_empty_corpus")
            self._bm25 = None
            return

        corpus = [_tokenize(c.content) for c in self._chunks]
        try:
            from rank_bm25 import BM25Okapi  # type: ignore

            self._bm25 = BM25Okapi(corpus)
            logger.info("bm25_index_built", extra={"chunk_count": len(self._chunks)})
        except ImportError:
            logger.warning("rank_bm25_not_installed_using_fallback")
            self._bm25 = _KeywordFallbackIndex(corpus)

    def search(self, query: str, top_k: int = 10) -> list[ScoredChunk]:
        """Return top_k chunks scored by BM25 relevance (descending score)."""
        if not self._chunks or self._bm25 is None:
            return []

        tokens = _tokenize(query)
        if not tokens:
            return []

        try:
            scores: list[float] = list(self._bm25.get_scores(tokens))
        except Exception as exc:
            logger.warning("bm25_search_error", extra={"error": str(exc)})
            return []

        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results: list[ScoredChunk] = []
        for idx, score in indexed[:top_k]:
            if score > 0:
                results.append(ScoredChunk(chunk=self._chunks[idx], score=float(score)))

        return results


class _KeywordFallbackIndex:
    """Simple keyword overlap fallback when rank_bm25 is unavailable."""

    def __init__(self, corpus: list[list[str]]) -> None:
        self._corpus = corpus

    def get_scores(self, tokens: list[str]) -> list[float]:
        query_set = set(tokens)
        scores: list[float] = []
        for doc_tokens in self._corpus:
            doc_set = set(doc_tokens)
            overlap = len(query_set & doc_set)
            denom = max(len(query_set), 1)
            scores.append(overlap / denom)
        return scores
