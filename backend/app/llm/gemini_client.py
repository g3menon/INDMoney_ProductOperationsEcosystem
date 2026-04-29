"""Gemini client wrapper with primary/fallback key (R10)."""

from __future__ import annotations

import asyncio
import logging

import google.generativeai as genai

from app.core.config import Settings
from app.core.context import correlation_id as _cid_var

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _configure(self, tier: str) -> None:
        key = self._settings.gemini_api_key if tier == "primary" else self._settings.gemini_api_key_fallback
        if not key:
            raise RuntimeError(f"gemini_api_key_missing_{tier}")
        genai.configure(api_key=key)

    def _generate_text_sync(self, prompt: str, model: str | None = None) -> str:
        try:
            self._configure("primary")
            m = genai.GenerativeModel(model or self._settings.gemini_model)
            resp = m.generate_content(prompt)
            return (resp.text or "").strip()
        except Exception as exc:
            msg = str(exc).lower()
            key_specific = any(s in msg for s in ("rate", "quota", "billing", "exhaust", "429", "resource"))
            if not key_specific:
                raise
            logger.warning("gemini_primary_failed_try_fallback", extra={"correlation_id": _cid_var.get()})
            self._configure("fallback")
            m = genai.GenerativeModel(model or self._settings.gemini_model)
            resp = m.generate_content(prompt)
            return (resp.text or "").strip()

    async def generate_text(self, prompt: str, model: str | None = None) -> str:
        return await asyncio.to_thread(self._generate_text_sync, prompt, model)
