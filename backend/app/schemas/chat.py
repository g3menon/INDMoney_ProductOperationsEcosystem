"""Customer chat schemas (Phase 3).

Phase 3 definition of done:
- text chat runtime
- prompt chips
- chat persistence (session + message history)
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ChatRole = Literal["user", "assistant"]


class ChatMessage(BaseModel):
    id: str
    session_id: str
    role: ChatRole
    content: str = Field(min_length=1, max_length=4000)
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class ChatMessageRequest(BaseModel):
    # When omitted, the backend will create a new session.
    session_id: str | None = Field(default=None)
    message: str = Field(min_length=1, max_length=2000)


class ChatMessageResult(BaseModel):
    session_id: str
    assistant_message: str
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class PromptChip(BaseModel):
    id: str
    label: str
    prompt: str
