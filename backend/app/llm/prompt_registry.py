"""Central prompt registry (Phase 2: Weekly Pulse prompts; Phase 4: RAG answer prompts).

All major prompt templates live here for versioned auditing (Rules R9).
"""

from __future__ import annotations


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
