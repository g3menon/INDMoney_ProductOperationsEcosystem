"""Central prompt registry (Phase 2: Weekly Pulse prompts)."""

from __future__ import annotations


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
