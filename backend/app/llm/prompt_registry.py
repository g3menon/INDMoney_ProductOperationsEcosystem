"""Central prompt registry (Phase 2: Weekly Pulse prompts; Phase 4: RAG answer prompts
and structured MF metrics formatting helpers).

All major prompt templates live here for versioned auditing (Rules R9).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.rag import MFFundMetrics


# ---------------------------------------------------------------------------
# Phase 2 — Weekly Pulse prompts
# ---------------------------------------------------------------------------


def pulse_theme_prompt(normalized_reviews: list[str]) -> str:
    joined = "\n".join(f"- {t}" for t in normalized_reviews[:120])
    return (
        "You are a product operations analyst. Extract 3-6 recurring themes from the review list.\n"
        "Return JSON with keys: themes: [{theme, summary, count}], quotes: [{review_id, quote, rating}].\n"
        "Only use the provided review text; do not invent. Keep summaries concise.\n\n"
        f"REVIEWS:\n{joined}\n"
    )


def weekly_pulse_prompt(theme_json: str) -> str:
    return (
        "You are generating a Weekly Pulse for a PM dashboard.\n"
        "Given the extracted themes and quotes (JSON), produce JSON with:\n"
        "narrative (short), recommended_actions (3-6 bullets), themes (pass through), quotes (pass through).\n"
        "Do NOT include fee explainer six-bullet tutorial content.\n\n"
        f"THEMES_AND_QUOTES_JSON:\n{theme_json}\n"
    )


# ---------------------------------------------------------------------------
# Phase 4 — RAG answer prompts (Rules R9, R14)
# ---------------------------------------------------------------------------

_RAG_SYSTEM_INSTRUCTIONS = (
    "You are a helpful assistant for Groww customers. "
    "Answer ONLY using the provided source passages. "
    "Do NOT invent fees, fund details, or facts not present in the sources. "
    "If the sources do not contain enough information, say so clearly. "
    "Keep answers concise (3-6 sentences or a short list). "
    "End every response with: 'This is general information only, not personalised financial advice.'"
)

_INTENT_CONTEXT: dict[str, str] = {
    "mf_query": "The customer is asking about mutual fund details (categories, strategies, suitability).",
    "fee_query": "The customer is asking about mutual fund fees: expense ratio, exit load, or cost comparison.",
    "hybrid_query": (
        "The customer is asking about both mutual fund details AND fees. "
        "Answer both parts clearly in a single response."
    ),
    "direct_metric_query": (
        "The customer is asking for a specific fund metric. "
        "Lead with the structured metric facts provided, then supplement with source context."
    ),
    "out_of_scope": "The customer's question may be only partially covered by the sources.",
}


def rag_answer_prompt(
    query: str,
    context_blocks: list[str],
    intent: str,
) -> str:
    """Build a bounded RAG answer prompt (Rules R3, R14).

    Args:
        query: The raw customer message.
        context_blocks: List of strings like "[Source: Title]\nchunk text...".
        intent: Classified intent label for extra instruction context.
    """
    intent_note = _INTENT_CONTEXT.get(intent, "")
    context_text = "\n\n---\n\n".join(context_blocks)

    return (
        f"{_RAG_SYSTEM_INSTRUCTIONS}\n\n"
        f"Intent note: {intent_note}\n\n"
        "SOURCE PASSAGES:\n"
        f"{context_text}\n\n"
        "---\n"
        f"Customer question: {query}\n\n"
        "Answer (use only the sources above):"
    )


def hybrid_answer_prompt(
    query: str,
    metrics_block: str,
    context_blocks: list[str],
    intent: str,
) -> str:
    """Build a hybrid prompt that combines structured metric facts + RAG passages.

    The metrics block is injected as a high-confidence structured source so the
    LLM leads with facts rather than inferring from narrative text.
    """
    intent_note = _INTENT_CONTEXT.get(intent, "")
    rag_context = "\n\n---\n\n".join(context_blocks)

    return (
        f"{_RAG_SYSTEM_INSTRUCTIONS}\n\n"
        f"Intent note: {intent_note}\n\n"
        "STRUCTURED FUND METRICS (high confidence — use these for specific figures):\n"
        f"{metrics_block}\n\n"
        "---\n\n"
        "SOURCE PASSAGES (use for explanatory context and narrative):\n"
        f"{rag_context}\n\n"
        "---\n"
        f"Customer question: {query}\n\n"
        "Answer (lead with structured facts where available; use passages for explanation):"
    )


# ---------------------------------------------------------------------------
# Phase 4 extended — Structured MF metrics formatting
# ---------------------------------------------------------------------------

_UNAVAILABLE = "not available (requires live page data)"


def format_metrics_block(metrics: "MFFundMetrics") -> str:
    """Format MFFundMetrics as a clean, LLM-readable structured block.

    Used both as the structured answer payload and as the metrics context
    injected into hybrid_answer_prompt().
    """
    lines: list[str] = [f"Fund: {metrics.fund_name}"]

    if metrics.amc:
        lines.append(f"AMC: {metrics.amc}")
    if metrics.category:
        sub = f" ({metrics.sub_category})" if metrics.sub_category else ""
        lines.append(f"Category: {metrics.category}{sub}")
    if metrics.plan or metrics.option:
        plan_opt = " / ".join(filter(None, [metrics.plan, metrics.option]))
        lines.append(f"Plan / Option: {plan_opt}")
    if metrics.risk_level:
        lines.append(f"Risk Level: {metrics.risk_level}")
    if metrics.benchmark:
        lines.append(f"Benchmark: {metrics.benchmark}")

    # Expense ratio
    if metrics.expense_ratio_pct is not None:
        per_10k = metrics.expense_ratio_pct * 100
        lines.append(
            f"Expense Ratio (TER): {metrics.expense_ratio_pct}% per annum"
            f" (~\u20b9{per_10k:.0f}/yr per \u20b910,000 invested)"
        )
    else:
        lines.append(f"Expense Ratio (TER): {_UNAVAILABLE}")

    # Exit load
    if metrics.exit_load_pct is not None:
        window = (
            f"within {metrics.exit_load_window_days} days"
            if metrics.exit_load_window_days
            else ""
        )
        load_line = f"Exit Load: {metrics.exit_load_pct}% {window}".strip()
        if metrics.exit_load_description:
            load_line += f" — {metrics.exit_load_description}"
        lines.append(load_line)
    elif metrics.exit_load_description:
        lines.append(f"Exit Load: {metrics.exit_load_description}")
    else:
        lines.append(f"Exit Load: {_UNAVAILABLE}")

    # Minimums
    if metrics.min_sip_amount is not None:
        lines.append(f"Minimum SIP: \u20b9{metrics.min_sip_amount:,.0f}")
    if metrics.min_lumpsum_amount is not None:
        lines.append(f"Minimum Lump Sum: \u20b9{metrics.min_lumpsum_amount:,.0f}")

    # NAV / AUM (live data; often None for fixture-based runs)
    if metrics.nav is not None:
        date_str = f" as of {metrics.nav_date}" if metrics.nav_date else ""
        lines.append(f"NAV: \u20b9{metrics.nav:.2f}{date_str}")
    if metrics.aum_cr is not None:
        lines.append(f"AUM: \u20b9{metrics.aum_cr:,.0f} crore")
    if metrics.rating:
        lines.append(f"Rating: {metrics.rating}")

    # Returns
    r = metrics.returns
    if r:
        parts: list[str] = []
        if r.one_month is not None:
            parts.append(f"1M: {r.one_month}%")
        if r.three_month is not None:
            parts.append(f"3M: {r.three_month}%")
        if r.six_month is not None:
            parts.append(f"6M: {r.six_month}%")
        if r.one_year is not None:
            parts.append(f"1Y: {r.one_year}%")
        if r.three_year is not None:
            parts.append(f"3Y: {r.three_year}%")
        if r.five_year is not None:
            parts.append(f"5Y: {r.five_year}%")
        if r.since_inception is not None:
            parts.append(f"SI: {r.since_inception}%")
        if parts:
            lines.append(f"Returns (annualised): {' | '.join(parts)}")

    # Top holdings
    if metrics.top_holdings:
        lines.append(f"Top Holdings ({len(metrics.top_holdings)} shown):")
        for h in metrics.top_holdings[:5]:
            w = f" {h.weight_pct}%" if h.weight_pct is not None else ""
            sec = f" [{h.sector}]" if h.sector else ""
            lines.append(f"  \u2022 {h.name}{w}{sec}")

    # Sector allocation
    if metrics.sector_allocation:
        lines.append("Sector Allocation:")
        for s in metrics.sector_allocation[:5]:
            w = f" {s.weight_pct}%" if s.weight_pct is not None else ""
            lines.append(f"  \u2022 {s.sector}{w}")

    # Asset allocation
    if metrics.asset_allocation:
        parts_aa = [f"{k}: {v}%" for k, v in list(metrics.asset_allocation.items())[:4]]
        lines.append(f"Asset Allocation: {', '.join(parts_aa)}")

    lines.append(f"Source: {metrics.source_url}")
    return "\n".join(lines)
