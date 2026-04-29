"""Grounded answer composition for Phase 4 RAG (Rules R1-R6, R12, R14, P4.3-P4.5).

Composes a final answer from retrieved chunks using Gemini 2.5 Flash.
Citations are carried end-to-end from chunk metadata (Rules R12, P4.7).

Extended for structured metrics:
- compose_structured_answer(): deterministic, no LLM, for direct_metric_query
  when a fund is matched in the metrics store.
- compose_hybrid_answer(): structured metrics block + RAG chunks → Gemini,
  for hybrid_query or direct_metric_query with explanatory context needed.

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

from app.schemas.rag import CitationSource, MFFundMetrics, ScoredChunk

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.llm.prompt_registry import RAGAnswerContext

logger = logging.getLogger(__name__)

_DISCLAIMER = "This is general information only, not personalised financial advice."
_MAX_CONTEXT_CHARS = 2400
_MAX_CHUNKS_FOR_ANSWER = 5

# ---------------------------------------------------------------------------
# Metric field → query keyword mapping for targeted structured answers
# ---------------------------------------------------------------------------

_METRIC_FIELD_GROUPS: list[tuple[frozenset[str], str]] = [
    (frozenset(["expense ratio", "ter", "total expense ratio"]), "expense_ratio"),
    (frozenset(["exit load", "redemption fee", "exit fee"]), "exit_load"),
    (frozenset(["nav", "net asset value", "current nav"]), "nav"),
    (frozenset(["aum", "fund size", "corpus", "assets under"]), "aum"),
    (frozenset(["minimum sip", "min sip", "sip amount", "sip minimum"]), "min_sip"),
    (frozenset(["minimum lump", "lumpsum", "lump sum", "minimum investment"]), "min_lumpsum"),
    (frozenset(["top holdings", "holdings", "portfolio stocks", "portfolio companies"]), "top_holdings"),
    (frozenset(["sector allocation", "sector breakdown"]), "sector_allocation"),
    (frozenset(["asset allocation", "instrument allocation"]), "asset_allocation"),
    (frozenset(["returns", "performance", "cagr", "1 year", "3 year", "5 year"]), "returns"),
    (frozenset(["risk level", "riskometer", "risk"]), "risk_level"),
    (frozenset(["benchmark"]), "benchmark"),
    (frozenset(["rating", "star rating", "crisil", "morningstar"]), "rating"),
]
_UNAVAILABLE = "not available (requires live page data)"


@dataclass
class AnswerResult:
    answer: str
    citations: list[CitationSource] = field(default_factory=list)
    fallback: bool = False
    fallback_reason: str | None = None


# ---------------------------------------------------------------------------
# Helpers shared across compose functions
# ---------------------------------------------------------------------------


def _build_citations(chunks: list[ScoredChunk]) -> list[CitationSource]:
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
    if intent in ("mf_query", "direct_metric_query"):
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


# ---------------------------------------------------------------------------
# Structured (deterministic) answer — no LLM call
# ---------------------------------------------------------------------------


def _detect_requested_fields(query: str) -> list[str]:
    lower = query.lower()
    requested = [
        group_name
        for kw_set, group_name in _METRIC_FIELD_GROUPS
        if any(kw in lower for kw in kw_set)
    ]
    return requested or ["summary"]


def _render_field_lines(metrics: MFFundMetrics, fields: list[str]) -> list[str]:
    lines: list[str] = []
    is_summary = "summary" in fields

    if is_summary:
        lines.append(f"**{metrics.fund_name}**")
        if metrics.amc:
            lines.append(f"AMC: {metrics.amc}")
        if metrics.category:
            lines.append(f"Category: {metrics.category}")
        if metrics.plan:
            lines.append(f"Plan: {metrics.plan}")
        if metrics.risk_level:
            lines.append(f"Risk Level: {metrics.risk_level}")
    else:
        lines.append(f"**{metrics.fund_name}**")

    if "expense_ratio" in fields or is_summary:
        if metrics.expense_ratio_pct is not None:
            per_10k = metrics.expense_ratio_pct * 100
            lines.append(
                f"Expense Ratio (TER): {metrics.expense_ratio_pct}% per annum"
                f" (\u20b9{per_10k:.0f}/yr per \u20b910,000 invested)"
            )
        elif not is_summary:
            lines.append(f"Expense Ratio: {_UNAVAILABLE}")

    if "exit_load" in fields or is_summary:
        if metrics.exit_load_pct is not None:
            window = (
                f"within {metrics.exit_load_window_days} days"
                if metrics.exit_load_window_days
                else ""
            )
            lines.append(f"Exit Load: {metrics.exit_load_pct}% {window}".strip())
            if metrics.exit_load_description:
                lines.append(f"  ({metrics.exit_load_description})")
        elif metrics.exit_load_description:
            lines.append(f"Exit Load: {metrics.exit_load_description}")
        elif not is_summary:
            lines.append(f"Exit Load: {_UNAVAILABLE}")

    if "nav" in fields:
        if metrics.nav is not None:
            date_str = f" as of {metrics.nav_date}" if metrics.nav_date else ""
            lines.append(f"NAV: \u20b9{metrics.nav:.2f}{date_str}")
        else:
            lines.append(f"NAV: {_UNAVAILABLE}")

    if "aum" in fields:
        if metrics.aum_cr is not None:
            lines.append(f"AUM: \u20b9{metrics.aum_cr:,.0f} crore")
        else:
            lines.append(f"AUM: {_UNAVAILABLE}")

    if "min_sip" in fields or is_summary:
        if metrics.min_sip_amount is not None:
            lines.append(f"Minimum SIP: \u20b9{metrics.min_sip_amount:,.0f}")

    if "min_lumpsum" in fields or is_summary:
        if metrics.min_lumpsum_amount is not None:
            lines.append(f"Minimum Lump Sum: \u20b9{metrics.min_lumpsum_amount:,.0f}")

    if "risk_level" in fields and not is_summary:
        lines.append(f"Risk Level: {metrics.risk_level or _UNAVAILABLE}")

    if "benchmark" in fields or is_summary:
        if metrics.benchmark:
            lines.append(f"Benchmark: {metrics.benchmark}")

    if "rating" in fields:
        lines.append(f"Rating: {metrics.rating or _UNAVAILABLE}")

    if "returns" in fields:
        r = metrics.returns
        if r:
            parts: list[str] = []
            if r.one_month is not None:
                parts.append(f"1M {r.one_month}%")
            if r.three_month is not None:
                parts.append(f"3M {r.three_month}%")
            if r.six_month is not None:
                parts.append(f"6M {r.six_month}%")
            if r.one_year is not None:
                parts.append(f"1Y {r.one_year}%")
            if r.three_year is not None:
                parts.append(f"3Y {r.three_year}%")
            if r.five_year is not None:
                parts.append(f"5Y {r.five_year}%")
            if parts:
                lines.append(f"Returns (annualised): {' | '.join(parts)}")
            else:
                lines.append(f"Returns: {_UNAVAILABLE}")
        else:
            lines.append(f"Returns: {_UNAVAILABLE}")

    if "top_holdings" in fields:
        if metrics.top_holdings:
            lines.append("Top Holdings:")
            for h in metrics.top_holdings[:5]:
                w = f" ({h.weight_pct}%)" if h.weight_pct is not None else ""
                lines.append(f"  \u2022 {h.name}{w}")
        else:
            lines.append(f"Top Holdings: {_UNAVAILABLE}")

    if "sector_allocation" in fields:
        if metrics.sector_allocation:
            lines.append("Sector Allocation:")
            for s in metrics.sector_allocation[:5]:
                w = f" ({s.weight_pct}%)" if s.weight_pct is not None else ""
                lines.append(f"  \u2022 {s.sector}{w}")
        else:
            lines.append(f"Sector Allocation: {_UNAVAILABLE}")

    if "asset_allocation" in fields:
        if metrics.asset_allocation:
            parts_aa = [f"{k}: {v}%" for k, v in list(metrics.asset_allocation.items())[:4]]
            lines.append(f"Asset Allocation: {', '.join(parts_aa)}")
        else:
            lines.append(f"Asset Allocation: {_UNAVAILABLE}")

    lines.append(f"Source: {metrics.source_url}")
    return lines


def compose_structured_answer(
    query: str,
    metrics: MFFundMetrics,
    intent: str,
) -> AnswerResult:
    """Generate a deterministic structured answer from MFFundMetrics.

    No LLM call is made.  Fields unavailable without JS rendering are noted
    inline rather than omitted, so the customer understands the limitation.
    """
    fields = _detect_requested_fields(query)
    body = "\n".join(_render_field_lines(metrics, fields))
    answer = f"{body}\n\n{_DISCLAIMER}"
    citation = CitationSource(
        source_url=metrics.source_url,
        doc_type="mutual_fund_page",
        title=metrics.fund_name,
        last_checked=metrics.last_checked,
    )
    return AnswerResult(answer=answer, citations=[citation])


# ---------------------------------------------------------------------------
# RAG grounded answer (existing, preserved)
# ---------------------------------------------------------------------------


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

    raw_answer = await _call_gemini(prompt, settings)
    logger.info(
        "rag_answer_composed",
        extra={"intent": intent, "fallback": raw_answer is None},
    )

    if not raw_answer:
        return _safe_fallback(intent, query, "gemini_unavailable")

    answer = raw_answer if _DISCLAIMER in raw_answer else f"{raw_answer}\n\n{_DISCLAIMER}"
    return AnswerResult(answer=answer, citations=_build_citations(used_chunks))


# ---------------------------------------------------------------------------
# Hybrid answer — structured metrics block + RAG chunks → Gemini
# ---------------------------------------------------------------------------


async def compose_hybrid_answer(
    query: str,
    metrics: MFFundMetrics,
    chunks: list[ScoredChunk],
    intent: str,
    settings: "Settings",
) -> AnswerResult:
    """Compose an answer that leads with structured metric facts then uses RAG
    chunks for explanatory narrative.

    If Gemini is unavailable, falls back to the deterministic structured answer.
    """
    from app.llm.prompt_registry import format_metrics_block, hybrid_answer_prompt

    metrics_block = format_metrics_block(metrics)

    context_parts: list[str] = []
    total_chars = 0
    used_chunks: list[ScoredChunk] = []
    for sc in (chunks or [])[:_MAX_CHUNKS_FOR_ANSWER]:
        chunk_text = sc.chunk.content[:500]
        if total_chars + len(chunk_text) > _MAX_CONTEXT_CHARS:
            break
        context_parts.append(f"[Source: {sc.chunk.title}]\n{chunk_text}")
        total_chars += len(chunk_text)
        used_chunks.append(sc)

    if not context_parts:
        # No RAG context — fall back to deterministic structured answer.
        return compose_structured_answer(query, metrics, intent)

    prompt = hybrid_answer_prompt(
        query=query,
        metrics_block=metrics_block,
        context_blocks=context_parts,
        intent=intent,
    )

    raw_answer = await _call_gemini(prompt, settings)
    logger.info(
        "hybrid_answer_composed",
        extra={"intent": intent, "fallback": raw_answer is None},
    )

    if not raw_answer:
        return compose_structured_answer(query, metrics, intent)

    answer = raw_answer if _DISCLAIMER in raw_answer else f"{raw_answer}\n\n{_DISCLAIMER}"

    # Citations: always include the metrics source + any RAG sources.
    citations: list[CitationSource] = [
        CitationSource(
            source_url=metrics.source_url,
            doc_type="mutual_fund_page",
            title=metrics.fund_name,
            last_checked=metrics.last_checked,
        )
    ]
    for sc in used_chunks:
        url = sc.chunk.source_url
        if url != metrics.source_url and not any(c.source_url == url for c in citations):
            citations.append(
                CitationSource(
                    source_url=url,
                    doc_type=sc.chunk.doc_type,
                    title=sc.chunk.title,
                    last_checked=sc.chunk.last_checked,
                )
            )

    return AnswerResult(answer=answer, citations=citations)


# ---------------------------------------------------------------------------
# Shared Gemini call helper
# ---------------------------------------------------------------------------


async def _call_gemini(prompt: str, settings: "Settings") -> str | None:
    def _generate() -> str | None:
        try:
            import google.generativeai as genai  # type: ignore

            key = settings.gemini_api_key
            fallback_key = settings.gemini_api_key_fallback
            if not key:
                return None

            def _run(api_key: str) -> str:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(settings.gemini_model)
                resp = model.generate_content(prompt)
                return (resp.text or "").strip()

            try:
                return _run(key)
            except Exception as exc:
                msg = str(exc).lower()
                if fallback_key and any(
                    s in msg for s in ("rate", "quota", "billing", "429", "exhaust")
                ):
                    logger.warning("gemini_primary_failed_using_fallback")
                    return _run(fallback_key)
                raise
        except Exception as exc:
            logger.warning("gemini_call_error", extra={"error": str(exc)[:100]})
            return None

    t0 = time.monotonic()
    result = await asyncio.to_thread(_generate)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.debug("gemini_call_done", extra={"elapsed_ms": elapsed_ms, "ok": result is not None})
    return result
