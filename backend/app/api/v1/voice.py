"""Voice API — Phase 8.

POST /api/v1/voice/message
  Accepts multipart/form-data: audio file + optional session_id.
  Returns transcript, assistant text, and base64-encoded MP3 audio chunks.

No business logic here — all orchestration is delegated to VoiceAdapterService.
"""

from __future__ import annotations

import base64
import logging
from functools import lru_cache

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.integrations.google.stt_client import STTError, SpeechToText
from app.integrations.google.tts_client import TTSError, TextToSpeech
from app.schemas.common import APIEnvelope
from app.schemas.voice import VoiceMessageResponse
from app.services.voice.voice_adapter_service import VoiceAdapterService, VoiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice")


# ── Singleton factories (instantiated once per process) ───────────────────────


@lru_cache(maxsize=1)
def _get_stt() -> SpeechToText:
    return SpeechToText()


@lru_cache(maxsize=1)
def _get_tts() -> TextToSpeech:
    return TextToSpeech()


# ── FastAPI dependency providers ──────────────────────────────────────────────


def get_stt_client() -> SpeechToText:
    return _get_stt()


def get_tts_client() -> TextToSpeech:
    return _get_tts()


def get_voice_adapter(
    stt: SpeechToText = Depends(get_stt_client),
    tts: TextToSpeech = Depends(get_tts_client),
    settings: Settings = Depends(get_settings),
) -> VoiceAdapterService:
    return VoiceAdapterService(stt=stt, tts=tts, settings=settings)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("")
async def voice_root() -> JSONResponse:
    return JSONResponse(status_code=200, content={"detail": "voice_api_phase_8"})


@router.post("/message", response_model=APIEnvelope[VoiceMessageResponse])
async def post_voice_message(
    audio: UploadFile,
    session_id: str | None = Form(default=None),
    adapter: VoiceAdapterService = Depends(get_voice_adapter),
) -> APIEnvelope[VoiceMessageResponse]:
    """Process one voice turn.

    Accepts:
        audio: Audio file (WEBM_OPUS from browser MediaRecorder /
            Streamlit st.audio_input).
        session_id: Optional chat session ID. A new session is started if
            omitted.

    Returns:
        transcript, assistant_text, and base64-encoded MP3 audio_chunks.
    """
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="audio file is empty")

    effective_session_id = session_id or _new_session_id()

    try:
        result = await adapter.process(
            audio_chunk=audio_bytes,
            session_id=effective_session_id,
        )
    except STTError as exc:
        logger.warning("voice_route_stt_error", extra={"reason": exc.reason})
        raise HTTPException(status_code=422, detail=f"stt_error: {exc.reason}") from exc
    except TTSError as exc:
        logger.warning("voice_route_tts_error", extra={"reason": exc.reason})
        raise HTTPException(status_code=502, detail=f"tts_error: {exc.reason}") from exc
    except VoiceError as exc:
        logger.error("voice_route_pipeline_error", extra={"reason": exc.reason})
        raise HTTPException(status_code=500, detail=f"voice_error: {exc.reason}") from exc

    encoded_chunks = [
        base64.b64encode(chunk).decode("utf-8") for chunk in result["audio_chunks"]
    ]

    return APIEnvelope(
        success=True,
        message="voice_message",
        data=VoiceMessageResponse(
            transcript=result["transcript"],
            assistant_text=result["assistant_text"],
            audio_chunks=encoded_chunks,
        ),
    )


def _new_session_id() -> str:
    from uuid import uuid4

    return str(uuid4())
