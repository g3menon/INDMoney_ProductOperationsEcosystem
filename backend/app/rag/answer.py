"""Grounded answer composition for Phase 4 RAG (Rules R1-R6, R12, R14, P4.3-P4.5).

Composes a final answer from retrieved chunks using Gemini 2.5 Flash.
Citations are carried end-to-end from chunk metadata (Rules R12, P4.7).

Failure paths:
- No chunks → safe fallback (Rules R1, P4.3).
- Gemini failure → deterministic bounded fallback, never invented content.
- Disallowed intent → refuse early (Rules R13).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.schemas.rag import CitationSource, ScoredChunk

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.llm.prompt_registry import RAGAnswerContext

logger = logging.getLogger(__name__)

_DISCLAIMER = "This is general information only, not personalised financial advice."
_MAX_CONTEXT_CHARS = 2400  # total chars sent to LLM across all chunks (Rules R3)
_MAX_CHUNKS_FOR_ANSWER = 5


@dataclass
class AnswerResult:
    answer: str
    citations: list[CitationSource] = field(default_factory=list)
    fallback: bool = False
    fallback_reason: str | None = None


def _build_citations(chunks: list[ScoredChunk]) -> list[CitationSource]:
    """Deduplicate citations by source URL while preserving order."""
    seen: set[str] = set()
    citations: list[CitationSource] = []
    for sc in chunks:
        url = sc.chunk.source_url
        if url not in seen:
            seen.add(url)
            quote = sc.chunk.content[:120].replace("\n", " ").strip()
            citations.append(
                CitationSource(
                    source_url=url,
                    doc_type=sc.chunk.doc_type,
                    title=sc.chunk.title,
                    last_checked=sc.chunk.last_checked,
                    relevant_quote=quote if len(quote) >= 20 else None,
                )
            )
    return citations


def _safe_fallback(intent: str, query: str, reason: str) -> AnswerResult:
    """Return a bounded, safe fallback response without invented content."""
    if intent in ("mf_query",):
        msg = (
            "I can help with mutual fund questions. Could you be more specific about "
            "what you want to know—fund category, performance comparison, or something else? "
            f"{_DISCLAIMER}"
        )
    elif intent in ("fee_query",):
        msg = (
            "I can explain mutual fund fees such as expense ratios and exit loads. "
            "Please share which fund or fee type you have in mind and I will look it up. "
            f"{_DISCLAIMER}"
        )
    else:
        msg = (
            "I have information on Groww mutual funds and their fees. "
            "Try asking about a specific fund's expense ratio or exit load. "
            f"{_DISCLAIMER}"
        )
    return AnswerResult(answer=msg, fallback=True, fallback_reason=reason)


async def compose_grounded_answer(
    query: str,
    chunks: list[ScoredChunk],
    intent: str,
    settings: "Settings",
) -> AnswerResult:
    """Generate a grounded answer from retrieved chunks using Gemini."""
    from app.llm.prompt_registry import rag_answer_prompt

    if not chunks:
        return _safe_fallback(intent, query, "no_retrieval_hits")

    top_chunks = chunks[:_MAX_CHUNKS_FOR_ANSWER]
    citations = _build_citations(top_chunks)

    # Build bounded context for the LLM (Rules R3).
    context_parts: list[str] = []
    total_chars = 0
    used_chunks: list[ScoredChunk] = []
    for sc in top_chunks:
        chunk_text = sc.chunk.content[:600]
        if total_chars + len(chunk_text) > _MAX_CONTEXT_CHARS:
            break
        context_parts.append(f"[Source: {sc.chunk.title}]\n{chunk_text}")
        total_chars += len(chunk_text)
        used_chunks.append(sc)

    if not context_parts:
        return _safe_fallback(intent, query, "context_too_large")

    prompt = rag_answer_prompt(
        query=query,
        context_blocks=context_parts,
        intent=intent,
    )

    t0 = time.monotonic()

    def _call_gemini() -> str | None:
        try:
            import google.generativeai as genai  # type: ignore

            key = settings.gemini_api_key
            fallback_key = settings.gemini_api_key_fallback
            if not key:
                return None

            def _generate(api_key: str) -> str:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(settings.gemini_model)
                resp = model.generate_content(prompt)
                return (resp.text or "").strip()

            try:
                text = _generate(key)
                logger.debug("rag_answer_gemini_ok", extra={"tier": "primary", "len": len(text)})
                return text
            except Exception as exc:
                msg = str(exc).lower()
                if fallback_key and any(s in msg for s in ("rate", "quota", "billing", "429", "exhaust")):
                    logger.warning("rag_answer_gemini_primary_failed_fallback")
                    text = _generate(fallback_key)
                    logger.debug("rag_answer_gemini_ok", extra={"tier": "fallback", "len": len(text)})
                    return text
                raise
        except Exception as exc:
            logger.warning("rag_answer_gemini_error", extra={"error": str(exc)[:100]})
            return None

    raw_answer = await asyncio.to_thread(_call_gemini)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info("rag_answer_composed", extra={"intent": intent, "elapsed_ms": elapsed_ms, "fallback": raw_answer is None})

    if not raw_answer:
        return _safe_fallback(intent, query, "gemini_unavailable")

    # Ensure disclaimer is always present (Rules R6, P4.5).
    answer = raw_answer if _DISCLAIMER in raw_answer else f"{raw_answer}\n\n{_DISCLAIMER}"

    return AnswerResult(answer=answer, citations=_build_citations(used_chunks))
