"""Script-level LLM API throttler (token bucket).

Designed for batch scripts and embedding generation to avoid free-tier RPM caps.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class _Bucket:
    rpm: int
    tokens: float
    updated_at: float
    lock: asyncio.Lock


_buckets: dict[str, _Bucket] = {}


def _get_rpm_from_settings(provider: str, settings: "Settings | None") -> int:
    if settings is None:
        return 8 if provider == "gemini" else 25
    if provider == "groq":
        return int(settings.groq_rpm_limit)
    return int(settings.gemini_rpm_limit)


async def wait_for_slot(provider: str = "gemini", settings: "Settings | None" = None) -> None:
    """Block until a request slot is available for the given provider."""

    provider = (provider or "gemini").lower()
    rpm = max(1, _get_rpm_from_settings(provider, settings))
    refill_rate_per_s = rpm / 60.0  # tokens per second
    capacity = float(rpm)  # burst up to 1 minute

    b = _buckets.get(provider)
    if b is None or b.rpm != rpm:
        b = _Bucket(rpm=rpm, tokens=capacity, updated_at=time.monotonic(), lock=asyncio.Lock())
        _buckets[provider] = b

    waited_s_total = 0.0
    while True:
        async with b.lock:
            now = time.monotonic()
            elapsed = max(0.0, now - b.updated_at)
            b.tokens = min(capacity, b.tokens + elapsed * refill_rate_per_s)
            b.updated_at = now

            if b.tokens >= 1.0:
                b.tokens -= 1.0
                return

            # Need to wait until we have 1 token.
            needed = 1.0 - b.tokens
            wait_s = needed / refill_rate_per_s if refill_rate_per_s > 0 else 1.0

        # Outside lock while sleeping.
        wait_s = max(0.01, min(wait_s, 2.0))
        waited_s_total += wait_s
        if waited_s_total > 5.0:
            logger.warning(
                "llm_throttle_wait",
                extra={"provider": provider, "wait_s": int(waited_s_total)},
            )
        await asyncio.sleep(wait_s)

