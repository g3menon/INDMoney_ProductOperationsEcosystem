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
_CONTEXT_TOKEN_BUDGET = 2000

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
    (frozenset(["10 year", "ten year", "return calculator", "investment return"]), "returns"),
    (frozenset(["returns and rankings", "ranking", "rank"]), "returns_and_rankings"),
    (frozenset(["advanced ratios", "sharpe", "sortino", "alpha", "beta", "standard deviation"]), "advanced_ratios"),
    (frozenset(["fund management", "fund manager", "manager"]), "fund_management"),
    (frozenset(["risk level", "riskometer", "risk"]), "risk_level"),
    (frozenset(["benchmark"]), "benchmark"),
    (frozenset(["rating", "star rating", "crisil", "morningstar"]), "rating"),
]
_UNAVAILABLE = "not available in the current indexed source data"


@dataclass
class AnswerResult:
    answer: str
    citations: list[CitationSource] = field(default_factory=list)
    fallback: bool = False
    fallback_reason: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class LLMTextResult:
    text: str | None
    provider_used: str = "none"
    model_used: str | None = None
    fallback_used: bool = False
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
    if intent in ("mutual_fund_info_query", "direct_metric_query"):
        msg = (
            "I can help with mutual fund questions. Could you be more specific about "
            "what you want to know—fund category, performance comparison, or something else? "
            f"{_DISCLAIMER}"
        )
    elif intent == "product_review_query":
        msg = (
            "I can look up Play Store reviews and user feedback for this topic. "
            "Try rephrasing with a specific feature or time period — for example: "
            "'What do users say about the onboarding flow in recent reviews?' "
            f"{_DISCLAIMER}"
        )
    elif intent == "trend_query":
        msg = (
            "I can help with trend analysis across review periods. "
            "Try a question like: 'Are complaints about UPI rising this quarter?' "
            f"{_DISCLAIMER}"
        )
    elif intent == "issue_diagnosis_query":
        msg = (
            "I can help diagnose product issues from review data. "
            "Try asking: 'Why are crash reports increasing since version 5.2?' "
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
    logger.warning(
        "fallback_triggered",
        extra={"fallback": "safe_answer", "reason": reason, "intent": intent},
    )
    return AnswerResult(
        answer=msg,
        fallback=True,
        fallback_reason=reason,
        metadata={
            "provider_used": "none",
            "model_used": None,
            "fallback_used": True,
            "fallback_reason": reason,
        },
    )


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
            if metrics.nav_source_url:
                lines.append(f"NAV Source: {metrics.nav_source_url}")
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
            if r.ten_year is not None:
                parts.append(f"10Y {r.ten_year}%")
            if r.all_time is not None:
                parts.append(f"All {r.all_time}%")
            if parts:
                lines.append(f"Returns (annualised): {' | '.join(parts)}")
            else:
                lines.append(f"Returns: {_UNAVAILABLE}")
        else:
            lines.append(f"Returns: {_UNAVAILABLE}")

        if metrics.investment_returns:
            lines.append("Investment Return Calculator:")
            for row in metrics.investment_returns[:4]:
                total = f"\u20b9{row.total_investment:,.0f}" if row.total_investment is not None else "not available"
                current = f"\u20b9{row.current_value:,.0f}" if row.current_value is not None else "not available"
                ret = f"{row.return_pct}%" if row.return_pct is not None else "not available"
                lines.append(f"  \u2022 {row.period}: {total} became {current} ({ret})")

    if "returns_and_rankings" in fields:
        rr = metrics.returns_and_rankings
        if rr:
            if rr.fund_returns:
                parts = [f"{_period_label(k)} {v}%" for k, v in rr.fund_returns.items()]
                lines.append(f"Fund Returns: {' | '.join(parts)}")
            if rr.category_average:
                parts = [f"{_period_label(k)} {v}%" for k, v in rr.category_average.items()]
                lines.append(f"Category Average: {' | '.join(parts)}")
            if rr.rank:
                parts = [f"{_period_label(k)} #{v}" for k, v in rr.rank.items()]
                lines.append(f"Rank: {' | '.join(parts)}")
        else:
            lines.append(f"Returns and Rankings: {_UNAVAILABLE}")

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

    if "advanced_ratios" in fields:
        if metrics.advanced_ratios:
            parts = [f"{k.replace('_', ' ').title()}: {v}" for k, v in metrics.advanced_ratios.items()]
            lines.append(f"Advanced Ratios: {', '.join(parts)}")
        else:
            lines.append(f"Advanced Ratios: {_UNAVAILABLE}")

    if "fund_management" in fields:
        if metrics.fund_managers:
            lines.append("Fund Management:")
            for manager in metrics.fund_managers[:5]:
                tenure = f" ({manager.tenure})" if manager.tenure else ""
                lines.append(f"  \u2022 {manager.name}{tenure}")
                if manager.education:
                    lines.append(f"    Education: {manager.education}")
                if manager.experience:
                    lines.append(f"    Experience: {manager.experience}")
        else:
            lines.append(f"Fund Management: {_UNAVAILABLE}")

    lines.append(f"Source: {metrics.source_url}")
    return lines


def _period_label(period: str) -> str:
    return {
        "one_year": "1Y",
        "three_year": "3Y",
        "five_year": "5Y",
        "ten_year": "10Y",
        "all_time": "All",
    }.get(period, period.replace("_", " "))


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
    return AnswerResult(
        answer=answer,
        citations=[citation],
        metadata={
            "provider_used": "none",
            "model_used": None,
            "fallback_used": False,
            "fallback_reason": None,
        },
    )


# ---------------------------------------------------------------------------
# RAG grounded answer (existing, preserved)
# ---------------------------------------------------------------------------


async def compose_grounded_answer(
    query: str,
    chunks: list[ScoredChunk],
    intent: str,
    settings: "Settings",
) -> AnswerResult:
    """Generate a grounded answer from retrieved chunks using an LLM tier."""
    from app.llm.prompt_registry import rag_answer_prompt
    from app.llm.response_cache import (
        get_cached,
        log_cache_hit,
        log_cache_miss,
        make_cache_key,
        set_cached,
        should_bypass_cache,
    )
    from app.llm.task_router import assign_model_tier

    if not chunks:
        return _safe_fallback(intent, query, "no_retrieval_hits")

    tier = assign_model_tier(intent)  # mf_query/fee_query => standard; hybrid_query => heavy
    cache_key = make_cache_key(intent=intent, query=query, fund_doc_id=None)

    if not should_bypass_cache(settings, query):
        cached = get_cached(cache_key)
        if cached:
            log_cache_hit(intent, cache_key)
            used_chunks = _select_chunks_for_llm(chunks, settings)
            return AnswerResult(
                answer=cached,
                citations=_build_citations(used_chunks),
                metadata={
                    "provider_used": "none",
                    "model_used": None,
                    "fallback_used": False,
                    "fallback_reason": None,
                    "rag_chunks_sent_to_llm": len(used_chunks),
                },
            )
        log_cache_miss(intent)

    used_chunks = _select_chunks_for_llm(chunks, settings)
    context_parts, approx_tokens = _build_context_window(
        used_chunks,
        token_budget=_CONTEXT_TOKEN_BUDGET,
        chunk_char_limit=600,
    )
    logger.info(
        "rag_context_window",
        extra={"chunks_sent": len(context_parts), "approx_tokens": int(approx_tokens)},
    )

    if not context_parts:
        return _safe_fallback(intent, query, "context_too_large")

    prompt = rag_answer_prompt(
        query=query,
        context_blocks=context_parts,
        intent=intent,
    )

    llm_result = await _call_llm_text(prompt=prompt, settings=settings, tier=tier)
    raw_answer = llm_result.text
    logger.info(
        "rag_answer_composed",
        extra={"intent": intent, "fallback": raw_answer is None},
    )

    if not raw_answer:
        return _safe_fallback(intent, query, "llm_unavailable")

    answer = raw_answer if _DISCLAIMER in raw_answer else f"{raw_answer}\n\n{_DISCLAIMER}"
    if not should_bypass_cache(settings, query):
        # Grounded RAG answers: shorter TTL (Guardrail 1).
        set_cached(cache_key, answer, ttl=1800)
    return AnswerResult(
        answer=answer,
        citations=_build_citations(used_chunks),
        fallback=llm_result.fallback_used,
        fallback_reason=llm_result.fallback_reason,
        metadata={
            "provider_used": llm_result.provider_used,
            "model_used": llm_result.model_used,
            "fallback_used": llm_result.fallback_used,
            "fallback_reason": llm_result.fallback_reason,
            "rag_chunks_sent_to_llm": len(used_chunks),
        },
    )


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
    from app.llm.response_cache import (
        get_cached,
        log_cache_hit,
        log_cache_miss,
        make_cache_key,
        set_cached,
        should_bypass_cache,
    )
    from app.llm.task_router import assign_model_tier

    metrics_block = format_metrics_block(metrics)

    tier = assign_model_tier(intent)  # hybrid_query => heavy
    cache_key = make_cache_key(intent=intent, query=query, fund_doc_id=metrics.doc_id)

    if not should_bypass_cache(settings, query):
        cached = get_cached(cache_key)
        if cached:
            log_cache_hit(intent, cache_key)
            used_chunks = _select_chunks_for_llm(chunks or [], settings)
            return _hybrid_result_from_cached(
                answer=cached,
                metrics=metrics,
                used_chunks=used_chunks,
            )
        log_cache_miss(intent)

    used_chunks = _select_chunks_for_llm(chunks or [], settings)
    context_parts, approx_tokens = _build_hybrid_context_window(
        used_chunks,
        token_budget=_CONTEXT_TOKEN_BUDGET,
        chunk_char_limit=500,
    )
    logger.info(
        "rag_context_window",
        extra={"chunks_sent": len(context_parts), "approx_tokens": int(approx_tokens)},
    )

    if not context_parts:
        # No RAG context — fall back to deterministic structured answer.
        logger.warning(
            "fallback_triggered",
            extra={"fallback": "structured_answer", "reason": "no_rag_context", "intent": intent},
        )
        result = compose_structured_answer(query, metrics, intent)
        result.fallback = True
        result.fallback_reason = "no_rag_context"
        result.metadata.update({"fallback_used": True, "fallback_reason": "no_rag_context"})
        return result

    prompt = hybrid_answer_prompt(
        query=query,
        metrics_block=metrics_block,
        context_blocks=context_parts,
        intent=intent,
    )

    llm_result = await _call_llm_text(prompt=prompt, settings=settings, tier=tier)
    raw_answer = llm_result.text
    logger.info(
        "hybrid_answer_composed",
        extra={"intent": intent, "fallback": raw_answer is None},
    )

    if not raw_answer:
        logger.warning(
            "fallback_triggered",
            extra={"fallback": "structured_answer", "reason": "llm_unavailable", "intent": intent},
        )
        result = compose_structured_answer(query, metrics, intent)
        result.fallback = True
        result.fallback_reason = "llm_unavailable"
        result.metadata.update({"fallback_used": True, "fallback_reason": "llm_unavailable"})
        return result

    answer = raw_answer if _DISCLAIMER in raw_answer else f"{raw_answer}\n\n{_DISCLAIMER}"
    if not should_bypass_cache(settings, query):
        set_cached(cache_key, answer, ttl=1800)

    result = _hybrid_result_from_cached(answer=answer, metrics=metrics, used_chunks=used_chunks)
    result.fallback = llm_result.fallback_used
    result.fallback_reason = llm_result.fallback_reason
    result.metadata.update(
        {
            "provider_used": llm_result.provider_used,
            "model_used": llm_result.model_used,
            "fallback_used": llm_result.fallback_used,
            "fallback_reason": llm_result.fallback_reason,
            "rag_chunks_sent_to_llm": len(used_chunks),
        }
    )
    return result


def _approx_tokens(text: str) -> int:
    # Rough approximation: tokens ≈ words × 1.3
    words = len((text or "").split())
    return int(words * 1.3)


def _truncate_to_token_budget(text: str, remaining_tokens: int) -> str:
    if remaining_tokens <= 0:
        return ""
    max_words = max(1, int(remaining_tokens / 1.3))
    words = (text or "").split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip()


def _select_chunks_for_llm(
    chunks: list[ScoredChunk],
    settings: "Settings",
) -> list[ScoredChunk]:
    # Guardrail 2: cap chunks passed to LLM prompt.
    k = max(1, int(getattr(settings, "max_rag_chunks_for_llm", 3)))
    ranked = sorted(chunks or [], key=lambda sc: float(sc.score), reverse=True)
    selected = ranked[:k]
    # Keep deterministic ordering as ranked already high->low.
    # Note: chunk text truncation happens during context building.
    return selected


def _build_context_window(
    chunks: list[ScoredChunk],
    token_budget: int,
    chunk_char_limit: int,
) -> tuple[list[str], int]:
    context_parts: list[str] = []
    approx_total = 0

    for i, sc in enumerate(chunks):
        # Keep existing guardrail to avoid huge prompts; the token budget is the main control.
        # (Chunk content can be long; this keeps runtime + logs stable.)
        # Per-chunk character cap as a secondary safety limit.
        limit = max(200, int(chunk_char_limit))
        chunk_text = (sc.chunk.content or "")[:limit]
        part = f"[Source: {sc.chunk.title}]\n{chunk_text}"
        part_tokens = _approx_tokens(part)

        if approx_total + part_tokens <= token_budget:
            context_parts.append(part)
            approx_total += part_tokens
            continue

        # Truncate THIS chunk to fit remaining budget and stop (Guardrail 2).
        remaining = token_budget - approx_total
        truncated_body = _truncate_to_token_budget(part, remaining_tokens=remaining)
        truncated_body = truncated_body.strip()
        if truncated_body:
            context_parts.append(truncated_body)
            approx_total = token_budget
        break

    return context_parts, approx_total


def _build_hybrid_context_window(
    chunks: list[ScoredChunk],
    token_budget: int,
    chunk_char_limit: int,
) -> tuple[list[str], int]:
    context_parts: list[str] = []
    approx_total = 0

    for sc in chunks:
        limit = max(200, int(chunk_char_limit))
        chunk_text = (sc.chunk.content or "")[:limit]
        part = f"[Source: {sc.chunk.title} | Type: {sc.chunk.doc_type}]\n{chunk_text}"
        part_tokens = _approx_tokens(part)

        if approx_total + part_tokens <= token_budget:
            context_parts.append(part)
            approx_total += part_tokens
            continue

        remaining = token_budget - approx_total
        truncated_body = _truncate_to_token_budget(part, remaining_tokens=remaining)
        truncated_body = truncated_body.strip()
        if truncated_body:
            context_parts.append(truncated_body)
            approx_total = token_budget
        break

    return context_parts, approx_total


def _hybrid_result_from_cached(
    answer: str,
    metrics: MFFundMetrics,
    used_chunks: list[ScoredChunk],
) -> AnswerResult:
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
    return AnswerResult(
        answer=answer,
        citations=citations,
        metadata={
            "provider_used": "none",
            "model_used": None,
            "fallback_used": False,
            "fallback_reason": None,
            "rag_chunks_sent_to_llm": len(used_chunks),
        },
    )


async def _call_llm_text(prompt: str, settings: "Settings", tier: str) -> LLMTextResult:
    """Tier-based provider/model routing with fallback (Guardrail 4).

    Standard tier: Groq primary → Gemini fallback on failure/empty.
    Heavy tier: Gemini only (no Groq fallback needed for heavy workloads).
    """
    provider = "gemini" if tier == "heavy" else "groq"

    # --- Primary: Groq for standard tier ---
    if provider == "groq":
        try:
            from app.llm.groq_client import GroqClient

            client = GroqClient(settings)
            model = settings.llm_standard_model
            logger.info("llm_call_started", extra={"provider": "groq", "model": model, "tier": tier})
            raw = await asyncio.to_thread(client.generate_text, prompt, model)
            if raw:
                logger.info("llm_call_succeeded", extra={"provider": "groq", "model": model, "tier": tier})
                return LLMTextResult(text=raw.strip(), provider_used="groq", model_used=model)
            logger.warning("groq_returned_empty", extra={"tier": tier})
            logger.warning(
                "fallback_triggered",
                extra={"fallback": "gemini", "reason": "groq_empty_response", "tier": tier},
            )
        except Exception as exc:
            logger.warning(
                "groq_call_failed_falling_back_to_gemini",
                extra={"error": str(exc)[:120], "tier": tier},
            )
            logger.warning(
                "fallback_triggered",
                extra={"fallback": "gemini", "reason": "groq_call_failed", "tier": tier},
            )
        # Groq failed or returned empty — fall through to Gemini fallback

    # --- Primary for heavy tier / Fallback for standard tier: Gemini ---
    try:
        from app.llm.gemini_client import GeminiClient

        client = GeminiClient(settings)
        fallback_model = settings.gemini_model if tier != "heavy" else settings.llm_heavy_model
        logger.info("llm_call_started", extra={"provider": "gemini", "model": fallback_model, "tier": tier})
        result = await client.generate_text(prompt, model=fallback_model)
        if result:
            logger.info("llm_call_succeeded", extra={"provider": "gemini", "model": fallback_model, "tier": tier})
            return LLMTextResult(
                text=result.strip(),
                provider_used="gemini",
                model_used=fallback_model,
                fallback_used=tier != "heavy",
                fallback_reason="groq_unavailable" if tier != "heavy" else None,
            )
    except Exception as exc:
        logger.warning(
            "llm_call_error",
            extra={"error": str(exc)[:120], "tier": tier},
        )
        logger.warning(
            "fallback_triggered",
            extra={"fallback": "safe_answer", "reason": "llm_call_error", "tier": tier},
        )

    return LLMTextResult(text=None, fallback_used=True, fallback_reason="llm_unavailable")
