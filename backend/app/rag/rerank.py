"""Optional LLM-based reranking step (Phase 4, Rules R11, P4.6).

When enabled (use_rerank=True in retrieve.py), asks Gemini to score each candidate
chunk for relevance against the query, then re-orders by LLM score.

Reranking is optional and degrades gracefully: if Gemini key is absent or the
call fails, the original fusion-ranked order is returned (Rules G7).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.schemas.rag import ScoredChunk

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

_MAX_CHUNKS_TO_RERANK = 10
_RERANK_CONTENT_LIMIT = 300  # chars per chunk sent to LLM (Rules R3)


def _rerank_prompt(query: str, chunks: list[ScoredChunk]) -> str:
    lines = [f"Query: {query}\n\nRate each passage 0-10 for relevance. Return only a JSON array of integers."]
    for i, sc in enumerate(chunks):
        snippet = sc.chunk.content[:_RERANK_CONTENT_LIMIT].replace("\n", " ")
        lines.append(f"[{i}] {snippet}")
    return "\n".join(lines)


async def rerank(
    query: str,
    chunks: list[ScoredChunk],
    settings: "Settings",
    top_k: int = 5,
) -> list[ScoredChunk]:
    """LLM-rerank top candidates; fall back to original order on any error."""
    if not chunks:
        return []

    candidates = chunks[:_MAX_CHUNKS_TO_RERANK]

    if not settings.gemini_api_key:
        logger.debug("rerank_skipped_no_gemini_key")
        return candidates[:top_k]

    prompt = _rerank_prompt(query, candidates)

    def _call() -> list[int] | None:
        import json

        try:
            import google.generativeai as genai  # type: ignore

            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel(settings.gemini_model)
            resp = model.generate_content(prompt)
            text = (resp.text or "").strip()
            # Parse JSON array; handle markdown code fences.
            text = text.strip("`").strip()
            if text.startswith("json"):
                text = text[4:].strip()
            scores = json.loads(text)
            if isinstance(scores, list) and len(scores) == len(candidates):
                return [int(s) for s in scores]
        except Exception as exc:
            logger.warning("rerank_llm_error", extra={"error": str(exc)[:80]})
        return None

    scores = await asyncio.to_thread(_call)
    if scores is None:
        return candidates[:top_k]

    reranked = sorted(
        zip(candidates, scores),
        key=lambda x: x[1],
        reverse=True,
    )
    return [ScoredChunk(chunk=sc.chunk, score=float(s) / 10.0) for sc, s in reranked][:top_k]
