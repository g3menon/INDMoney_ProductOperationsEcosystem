"""Pydantic schemas for the voice API (Phase 8)."""

from __future__ import annotations

from pydantic import BaseModel


class VoiceMessageResponse(BaseModel):
    """Successful response from POST /api/v1/voice/message."""

    transcript: str
    """Text transcribed from the uploaded audio."""

    assistant_text: str
    """Full assistant reply text (same as typed-chat output)."""

    audio_chunks: list[str]
    """Base64-encoded MP3 bytes, one entry per synthesized segment."""
