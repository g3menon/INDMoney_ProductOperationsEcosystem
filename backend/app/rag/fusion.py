"""Reciprocal Rank Fusion (RRF) for hybrid BM25 + embedding retrieval (Phase 4, Rules R11).

RRF combines multiple ranked lists into a single fused ranking without requiring
normalised scores, making it robust to score distribution differences between
BM25 and cosine similarity.

Reference: Cormack, Clarke & Buettcher (SIGIR 2009).
"""

from __future__ import annotations

from app.schemas.rag import DocumentChunk, ScoredChunk

_DEFAULT_K = 60  # standard RRF smoothing constant


def reciprocal_rank_fusion(
    ranked_lists: list[list[ScoredChunk]],
    k: int = _DEFAULT_K,
) -> list[ScoredChunk]:
    """Fuse multiple ranked lists of ScoredChunk using RRF.

    Args:
        ranked_lists: Two or more lists, each sorted descending by score.
        k: RRF smoothing constant (higher → less aggressive top-rank boosting).

    Returns:
        A merged, deduplicated list sorted descending by fused RRF score.
    """
    rrf_scores: dict[str, float] = {}
    chunk_map: dict[str, "DocumentChunk"] = {}

    for ranked in ranked_lists:
        for rank, scored in enumerate(ranked):
            cid = scored.chunk.chunk_id
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            if cid not in chunk_map:
                chunk_map[cid] = scored.chunk

    merged = [
        ScoredChunk(chunk=chunk_map[cid], score=score)
        for cid, score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    ]
    return merged
