"""Google Cloud Text-to-Speech client (Phase 8).

Adapter boundary only — no business logic.
"""

from __future__ import annotations

import logging

from google.cloud import texttospeech

from app.core.context import correlation_id as _cid_var

logger = logging.getLogger(__name__)


class TTSError(Exception):
    """Raised when speech synthesis fails. Always carries a `reason` field."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class TextToSpeech:
    """Thin wrapper around ``google.cloud.texttospeech.TextToSpeechClient``.

    Instantiate once and reuse across requests.
    Voice: en-IN-Neural2-A; output: MP3.
    """

    _VOICE = texttospeech.VoiceSelectionParams(
        language_code="en-IN",
        name="en-IN-Neural2-A",
    )
    _AUDIO_CONFIG = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
    )

    def __init__(self) -> None:
        self._client = texttospeech.TextToSpeechClient()

    def synthesize(self, assistant_message: str) -> bytes:
        """Synthesize *assistant_message* to MP3 bytes.

        Args:
            assistant_message: Plain-text string to be spoken.

        Returns:
            MP3 audio bytes.

        Raises:
            TTSError: On any gRPC / API failure.
        """
        cid = _cid_var.get("-")

        synthesis_input = texttospeech.SynthesisInput(text=assistant_message)
        try:
            response = self._client.synthesize_speech(
                input=synthesis_input,
                voice=self._VOICE,
                audio_config=self._AUDIO_CONFIG,
            )
        except Exception as exc:
            logger.error(
                "tts_synthesize_failed",
                extra={"correlation_id": cid, "error": str(exc)[:200]},
            )
            raise TTSError(reason=str(exc)) from exc

        logger.info(
            "tts_synthesized",
            extra={
                "correlation_id": cid,
                "audio_bytes": len(response.audio_content),
            },
        )
        return response.audio_content
