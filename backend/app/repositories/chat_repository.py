"""Customer chat repository (Phase 3).

InMemoryChatRepository is the default for test/eval environments.
SupabaseChatRepository is used when CHAT_STORAGE_MODE=supabase.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone
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


class SupabaseChatRepository:
    """Supabase-backed chat repository using the existing Supabase client.

    Tables (already in schema):
      chat_sessions: id (uuid), created_at (timestamptz)
      chat_messages: id (uuid), session_id (fk), role (text),
                     content (text), created_at (timestamptz)
    """

    def __init__(self, settings: Settings) -> None:
        from supabase import Client, create_client

        self._client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )

    async def create_session(self) -> str:
        sid = f"CS-{uuid4().hex[:12].upper()}"
        now = datetime.now(timezone.utc).isoformat()
        self._client.table("chat_sessions").insert({"id": sid, "created_at": now}).execute()
        return sid

    async def add_message(self, session_id: str, role: ChatRole, content: str) -> ChatMessage:
        mid = f"MSG-{uuid4().hex[:12].upper()}"
        now = datetime.now(timezone.utc).isoformat()
        self._client.table("chat_messages").insert(
            {
                "id": mid,
                "session_id": session_id,
                "role": role,
                "content": content,
                "created_at": now,
            }
        ).execute()
        return ChatMessage(id=mid, session_id=session_id, role=role, content=content, created_at=now)

    async def get_history(self, session_id: str) -> list[ChatMessage]:
        res = (
            self._client.table("chat_messages")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .execute()
        )
        rows = res.data or []
        return [
            ChatMessage(
                id=r["id"],
                session_id=r["session_id"],
                role=r["role"],
                content=r["content"],
                created_at=r.get("created_at", ""),
            )
            for r in rows
        ]


_MEM_CHAT: InMemoryChatRepository | None = None


def get_chat_repository(settings: Settings) -> ChatRepository:
    """Return the appropriate chat repository based on CHAT_STORAGE_MODE.

    - CHAT_STORAGE_MODE=memory (or unset) → InMemoryChatRepository (default)
    - APP_ENV=test or eval              → InMemoryChatRepository (forced)
    - CHAT_STORAGE_MODE=supabase        → SupabaseChatRepository
    """
    global _MEM_CHAT
    storage_mode = os.getenv("CHAT_STORAGE_MODE", "").lower().strip()
    app_env = (settings.app_env or "").lower()

    use_mem = storage_mode in ("", "memory") or app_env in ("test", "eval")

    if use_mem:
        if _MEM_CHAT is None:
            _MEM_CHAT = InMemoryChatRepository()
        return _MEM_CHAT

    if storage_mode == "supabase":
        return SupabaseChatRepository(settings)

    # Unknown mode — fall back to in-memory.
    if _MEM_CHAT is None:
        _MEM_CHAT = InMemoryChatRepository()
    return _MEM_CHAT
