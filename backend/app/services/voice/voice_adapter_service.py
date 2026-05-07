"""Voice adapter service (Phase 8).

Thin orchestration only:
    STT.transcribe → customer_router_service.generate_customer_response → TTS.synthesize

No business logic lives here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.integrations.google.stt_client import STTError, SpeechToText
from app.integrations.google.tts_client import TTSError, TextToSpeech
from app.services.customer_router_service import generate_customer_response

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)


class VoiceError(Exception):
    """Top-level voice pipeline error. Always carries a `reason` field."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class VoiceAdapterService:
    """Orchestrates STT → chat runtime → TTS.

    Both *stt* and *tts* must be pre-constructed singletons passed in at
    construction time. This class adds no business logic of its own.
    """

    def __init__(
        self,
        stt: SpeechToText,
        tts: TextToSpeech,
        settings: "Settings",
    ) -> None:
        self._stt = stt
        self._tts = tts
        self._settings = settings

    async def process(
        self,
        audio_chunk: bytes,
        session_id: str,
        language_code: str = "en-IN",
    ) -> dict[str, object]:
        """Run the full voice pipeline for one user turn.

        Args:
            audio_chunk: Raw WEBM_OPUS audio bytes from the client.
            session_id: Chat session identifier.
            language_code: BCP-47 tag forwarded to STT.

        Returns:
            ``{"transcript": str, "assistant_text": str, "audio_chunks": list[bytes]}``

        Raises:
            STTError: Propagated from the STT client.
            TTSError: Propagated from the TTS client.
            VoiceError: Wraps unexpected failures in the chat runtime.
        """
        # ── 1. Speech → Text (sync gRPC, offloaded to thread) ────────────
        transcript: str = await asyncio.to_thread(
            self._stt.transcribe, audio_chunk, language_code
        )
        logger.info(
            "voice_adapter_stt_done",
            extra={"session_id": session_id, "transcript_len": len(transcript)},
        )

        # ── 2. Existing chat runtime (reuse, do NOT duplicate) ────────────
        try:
            assistant_text, _citations = await generate_customer_response(
                settings=self._settings,
                session_id=session_id,
                user_message=transcript,
            )
        except Exception as exc:
            logger.error(
                "voice_adapter_chat_error",
                extra={"session_id": session_id, "error": str(exc)[:200]},
            )
            raise VoiceError(reason=f"chat_runtime_error: {exc}") from exc

        logger.info(
            "voice_adapter_chat_done",
            extra={"session_id": session_id, "response_len": len(assistant_text)},
        )

        # ── 3. Text → Speech (sync gRPC, offloaded to thread) ────────────
        audio_bytes: bytes = await asyncio.to_thread(self._tts.synthesize, assistant_text)
        logger.info(
            "voice_adapter_tts_done",
            extra={"session_id": session_id, "audio_bytes": len(audio_bytes)},
        )

        return {
            "transcript": transcript,
            "assistant_text": assistant_text,
            "audio_chunks": [audio_bytes],
        }
