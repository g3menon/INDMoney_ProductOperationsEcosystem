"""Google Cloud Speech-to-Text client (Phase 8).

Adapter boundary only — no business logic.
"""

from __future__ import annotations

import logging

from google.cloud import speech

from app.core.context import correlation_id as _cid_var

logger = logging.getLogger(__name__)


class STTError(Exception):
    """Raised when transcription fails. Always carries a `reason` field."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class SpeechToText:
    """Thin wrapper around ``google.cloud.speech.SpeechClient``.

    Instantiate once and reuse across requests.
    """

    def __init__(self) -> None:
        self._client = speech.SpeechClient()

    def transcribe(self, audio_chunk: bytes, language_code: str = "en-IN") -> str:
        """Transcribe *audio_chunk* to text.

        Args:
            audio_chunk: Raw audio bytes in WEBM_OPUS encoding (browser
                MediaRecorder / Streamlit ``st.audio_input`` default).
            language_code: BCP-47 language tag; defaults to ``en-IN``.

        Returns:
            Transcribed text string.

        Raises:
            STTError: On any gRPC / API failure, or when no transcript is
                returned.
        """
        cid = _cid_var.get("-")

        audio = speech.RecognitionAudio(content=audio_chunk)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
            language_code=language_code,
            enable_automatic_punctuation=True,
        )

        try:
            response = self._client.recognize(config=config, audio=audio)
        except Exception as exc:
            logger.error(
                "stt_transcribe_failed",
                extra={"correlation_id": cid, "error": str(exc)[:200]},
            )
            raise STTError(reason=str(exc)) from exc

        if not response.results:
            logger.warning("stt_no_transcript", extra={"correlation_id": cid})
            raise STTError(reason="no_transcript_returned")

        transcript = response.results[0].alternatives[0].transcript
        logger.info(
            "stt_transcribed",
            extra={
                "correlation_id": cid,
                "transcript_len": len(transcript),
                "language_code": language_code,
            },
        )
        return transcript
