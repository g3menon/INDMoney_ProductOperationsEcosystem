"""Thread-safe in-memory LRU response cache with TTL for LLM outputs.

Guardrails:
- Cache key is computed by call sites as sha256(intent + normalized_query + fund_doc_id?).
- Cache can be bypassed in tests and debug/fixture modes.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)


_DEFAULT_MAX_ENTRIES = 200


class _LRUCacheTTL:
    def __init__(self, max_entries: int = _DEFAULT_MAX_ENTRIES) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        # key -> (expires_at_epoch_s, value)
        self._data: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._hit_count = 0
        self._miss_count = 0

    def get(self, key: str) -> str | None:
        now = time.time()
        with self._lock:
            item = self._data.get(key)
            if not item:
                self._miss_count += 1
                return None
            expires_at, value = item
            if expires_at <= now:
                # Expired.
                self._data.pop(key, None)
                self._miss_count += 1
                return None
            # LRU: mark as most-recent.
            self._data.move_to_end(key, last=True)
            self._hit_count += 1
            return value

    def set(self, key: str, value: str, ttl_s: int) -> None:
        expires_at = time.time() + max(1, int(ttl_s))
        with self._lock:
            self._data[key] = (expires_at, value)
            self._data.move_to_end(key, last=True)
            while len(self._data) > self._max_entries:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._hit_count = 0
            self._miss_count = 0

    def stats(self) -> dict:
        with self._lock:
            return {
                "hit_count": int(self._hit_count),
                "miss_count": int(self._miss_count),
                "current_size": int(len(self._data)),
            }


_CACHE = _LRUCacheTTL(max_entries=_DEFAULT_MAX_ENTRIES)


def normalize_query(query: str) -> str:
    """Normalize user query for stable caching.

    - Trim
    - Lowercase
    - Collapse whitespace
    """

    q = (query or "").strip().lower()
    return " ".join(q.split())


def make_cache_key(intent: str, query: str, fund_doc_id: str | None = None) -> str:
    norm = normalize_query(query)
    base = f"{intent}|{norm}"
    if fund_doc_id:
        base = f"{base}|{fund_doc_id}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def should_bypass_cache(settings: "Settings", query: str) -> bool:
    if (settings.app_env or "").lower() == "test":
        return True

    if not settings.llm_cache_enabled:
        return True

    # Fixture debug marker: allow deterministic debugging even when fixtures are on.
    if os.getenv("RAG_USE_FIXTURE", "").lower() in ("1", "true", "yes"):
        if (query or "").lstrip().startswith("##"):
            return True

    return False


def get_cached(key: str) -> str | None:
    return _CACHE.get(key)


def set_cached(key: str, value: str, ttl: int = 3600) -> None:
    _CACHE.set(key, value, ttl_s=ttl)


def cache_stats() -> dict:
    return _CACHE.stats()


def clear_cache() -> None:
    _CACHE.clear()


def log_cache_hit(intent: str, key: str) -> None:
    logger.info("llm_cache_hit", extra={"intent": intent, "key_prefix": (key or "")[:8]})


def log_cache_miss(intent: str) -> None:
    logger.info("llm_cache_miss", extra={"intent": intent})


def log_guardrails_active(settings: "Settings") -> None:
    """Startup summary log (Guardrail 6)."""

    logger.info(
        "llm_guardrails_active",
        extra={
            "cache_enabled": bool(settings.llm_cache_enabled),
            "max_rag_chunks": int(settings.max_rag_chunks_for_llm),
            "light_model": settings.llm_light_model,
            "heavy_model": settings.llm_heavy_model,
            "gemini_rpm_limit": int(settings.gemini_rpm_limit),
            "groq_rpm_limit": int(settings.groq_rpm_limit),
        },
    )

