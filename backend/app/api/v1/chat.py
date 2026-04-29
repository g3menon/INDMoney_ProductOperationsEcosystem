"""Customer chat APIs (Phase 3)."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.repositories.chat_repository import get_chat_repository
from app.schemas.chat import ChatMessage, ChatMessageRequest, ChatMessageResult, PromptChip
from app.schemas.common import APIEnvelope
from app.services.customer_router_service import generate_customer_response
from app.services.prompt_service import get_prompt_chips

router = APIRouter(prefix="/chat")


@router.post("/message", response_model=APIEnvelope[ChatMessageResult])
async def post_message(body: ChatMessageRequest) -> APIEnvelope[ChatMessageResult]:
    settings = get_settings()
    repo = get_chat_repository(settings)

    session_id = body.session_id or await repo.create_session()
    await repo.add_message(session_id=session_id, role="user", content=body.message)

    assistant = await generate_customer_response(settings=settings, session_id=session_id, user_message=body.message)
    assistant_msg = await repo.add_message(session_id=session_id, role="assistant", content=assistant)

    return APIEnvelope(
        success=True,
        message="chat_message",
        data=ChatMessageResult(session_id=session_id, assistant_message=assistant, created_at=assistant_msg.created_at),
    )


@router.get("/history/{session_id}", response_model=APIEnvelope[list[ChatMessage]])
async def history(session_id: str) -> APIEnvelope[list[ChatMessage]]:
    settings = get_settings()
    repo = get_chat_repository(settings)
    rows = await repo.get_history(session_id)
    return APIEnvelope(success=True, message="chat_history", data=rows)


@router.get("/prompts", response_model=APIEnvelope[list[PromptChip]])
async def prompts() -> APIEnvelope[list[PromptChip]]:
    settings = get_settings()
    chips = get_prompt_chips(settings)
    return APIEnvelope(success=True, message="chat_prompts", data=chips)
