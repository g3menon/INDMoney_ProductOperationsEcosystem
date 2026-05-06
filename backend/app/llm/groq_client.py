"""Groq client wrapper with primary/fallback key (R10)."""

from __future__ import annotations

import logging

from groq import Groq

from app.core.config import Settings
from app.core.context import correlation_id as _cid_var

logger = logging.getLogger(__name__)


class GroqClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _client(self, tier: str) -> Groq:
        key = self._settings.groq_api_key if tier == "primary" else self._settings.groq_api_key_fallback
        if not key:
            raise RuntimeError(f"groq_api_key_missing_{tier}")
        return Groq(api_key=key)

    def chat_json(self, prompt: str, model: str = "llama-3.1-70b-versatile") -> str:
        """One retry on key-specific failures (quota/rate/billing) to fallback tier."""
        try:
            c = self._client("primary")
            resp = c.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:
            msg = str(exc).lower()
            key_specific = any(s in msg for s in ("rate", "quota", "billing", "exhaust", "429"))
            if not key_specific:
                raise
            logger.warning("groq_primary_failed_try_fallback", extra={"correlation_id": _cid_var.get()})
            c = self._client("fallback")
            resp = c.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            return resp.choices[0].message.content or ""

    def generate_text(self, prompt: str, model: str | None = None) -> str | None:
        """Plain text completion — for RAG answers, not structured JSON."""
        _model = model or self._settings.llm_standard_model
        try:
            c = self._client("primary")
            response = c.chat.completions.create(
                model=_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=800,
            )
            return response.choices[0].message.content
        except Exception as exc:
            msg = str(exc).lower()
            key_specific = any(s in msg for s in ("rate", "quota", "billing", "exhaust", "429"))
            if not key_specific:
                logger.warning(
                    "groq_generate_text_primary_error_try_fallback",
                    extra={"error": str(exc)[:120], "model": _model},
                )
            else:
                logger.warning("groq_primary_failed_try_fallback", extra={"correlation_id": _cid_var.get()})
            try:
                c = self._client("fallback")
                response = c.chat.completions.create(
                    model=_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=800,
                )
                return response.choices[0].message.content
            except Exception as fallback_exc:
                logger.warning(
                    "groq_generate_text_error",
                    extra={"error": str(fallback_exc)[:120], "model": _model},
                )
                return None
