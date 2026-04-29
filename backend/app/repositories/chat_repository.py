"""Customer chat repository (Phase 3).

Phase 3 uses in-memory persistence so the text chat flow is runnable
in local/dev/test without requiring Supabase wiring yet.
"""

from __future__ import annotations

import os
import asyncio
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from app.core.config import Settings
from app.schemas.chat import ChatMessage, ChatRole


class ChatRepository(Protocol):
    async def create_session(self) -> str: ...

    async def add_message(self, session_id: str, role: ChatRole, content: str) -> ChatMessage: ...

    async def get_history(self, session_id: str) -> list[ChatMessage]: ...


@dataclass
class InMemoryChatRepository:
    _lock: asyncio.Lock
    _sessions: dict[str, list[ChatMessage]]

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._sessions = {}

    async def create_session(self) -> str:
        sid = f"CS-{uuid4().hex[:12].upper()}"
        async with self._lock:
            self._sessions[sid] = []
        return sid

    async def add_message(self, session_id: str, role: ChatRole, content: str) -> ChatMessage:
        msg = ChatMessage(
            id=f"MSG-{uuid4().hex[:12].upper()}",
            session_id=session_id,
            role=role,
            content=content,
        )
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = []
            self._sessions[session_id].append(msg)
        return msg

    async def get_history(self, session_id: str) -> list[ChatMessage]:
        async with self._lock:
            return list(self._sessions.get(session_id, []))


_MEM_CHAT: InMemoryChatRepository | None = None


def get_chat_repository(settings: Settings) -> ChatRepository:
    """
    For now, always return in-memory storage.

    This keeps Phase 3 runnable while the DB schema/migrations
    for chat persistence are not yet wired.
    """

    global _MEM_CHAT
    storage_mode = os.getenv("CHAT_STORAGE_MODE", "").lower().strip()
    use_mem = storage_mode in ("", "memory") or (settings.app_env or "").lower() in ("test", "eval")

    if use_mem:
        if _MEM_CHAT is None:
            _MEM_CHAT = InMemoryChatRepository()
        return _MEM_CHAT

    # Future: Supabase-backed implementation.
    if _MEM_CHAT is None:
        _MEM_CHAT = InMemoryChatRepository()
    return _MEM_CHAT
