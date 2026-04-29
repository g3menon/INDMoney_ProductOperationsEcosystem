"""Customer chat schemas (Phase 3 + Phase 4).

Phase 3: text chat runtime, prompt chips, session persistence.
Phase 4: citations attached to ChatMessageResult for grounded RAG answers.
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


class CitationSource(BaseModel):
    """Citation metadata returned with RAG-grounded answers (Phase 4, Rules R12/P4.7)."""

    source_url: str
    doc_type: str
    title: str
    last_checked: str
    relevant_quote: str | None = None


class ChatMessageResult(BaseModel):
    session_id: str
    assistant_message: str
    citations: list[CitationSource] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class PromptChip(BaseModel):
    id: str
    label: str
    prompt: str
