"""Customer routing skeleton (Phase 3).

Phase 3 definition of done only requires a stable text chat runtime with
prompt chips and chat persistence.

Until RAG (Phase 4) is wired, this service returns a bounded, deterministic
response that is safe and does not invent citations.
"""

from __future__ import annotations

from app.core.config import Settings


async def generate_customer_response(settings: Settings, session_id: str, user_message: str) -> str:
    _ = settings  # Phase 3: routing is rule-based until RAG is added.
    _ = session_id

    text = user_message.strip()
    lower = text.lower()

    disclaimer = "General information only, not financial advice."

    # Very small intent routing skeleton to keep the runtime stable.
    if any(k in lower for k in ["expense ratio", "exit load", "fees", "fee", "expense", "load"]):
        return (
            "Mutual fund fees commonly include the expense ratio and sometimes an exit load (depending on the fund). "
            "If you tell me which fund you’re looking at (or the expense ratio you see), I can help you interpret what it means in plain English. "
            f"{disclaimer}"
        )

    if any(k in lower for k in ["mutual fund", "sip", "index fund", "fund"]):
        return (
            "A mutual fund pools money from many investors and invests it in a diversified portfolio based on the fund’s objective. "
            "When you share what you want to achieve (growth, stability, or a timeframe), I can explain which fund characteristics matter and what to check. "
            f"{disclaimer}"
        )

    if any(k in lower for k in ["book", "booking", "advisor", "appointment", "schedule", "slot"]):
        return (
            "To book an advisor appointment, please share: (1) your preferred date/time window, (2) your mutual fund/fee question or goal, "
            "and (3) your timezone (we default to IST). After that, I’ll help you proceed with the booking flow. "
            f"{disclaimer}"
        )

    return (
        "I can help with mutual fund questions or fee/expense explanations. What are you looking for—mutual fund basics, or fees/expense ratio? "
        f"{disclaimer}"
    )
