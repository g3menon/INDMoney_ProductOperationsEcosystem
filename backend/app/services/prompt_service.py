"""Prompt chips service (Phase 3).

Phase 3 requires prompt chips to be available and to go through the same
validated runtime path as typed input (they are sent as normal chat messages).
"""

from __future__ import annotations

from app.core.config import Settings
from app.schemas.chat import PromptChip


def get_prompt_chips(_settings: Settings) -> list[PromptChip]:
    # Keep deterministic placeholders for Phase 3. Later phases can replace
    # chip sources with Weekly Pulse themes and RAG-derived suggestions.
    return [
        PromptChip(id="chip-mf-basics", label="Mutual fund basics", prompt="What is a mutual fund and how does it work?"),
        PromptChip(
            id="chip-fees-expense",
            label="Explain fees",
            prompt="Explain mutual fund expense ratio and other common fees in simple terms.",
        ),
        PromptChip(
            id="chip-booking",
            label="Book an advisor",
            prompt="I want to book an advisor appointment. What details do I need to provide?",
        ),
        PromptChip(
            id="chip-fees-before-invest",
            label="Fees before investing",
            prompt="What should I check on fees and charges before I invest in a mutual fund?",
        ),
    ]
