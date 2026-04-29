"""
Phase 3 automated evals: Customer text chat foundations (stub runtime).

Target: >= 85%
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class Check:
    id: str
    weight: float
    fn: Callable[[], bool]


class Phase3EvalReport(BaseModel):
    version: str = Field(default="phase3-v1")
    total_weight: float
    earned_weight: float
    score: float
    checks: list[dict[str, object]]


def _client() -> TestClient:
    from app.main import app as fastapi_app

    return TestClient(fastapi_app, raise_server_exceptions=True)


def _openapi_has_chat_paths() -> bool:
    c = _client()
    spec = c.get("/openapi.json").json()
    paths = spec.get("paths") or {}
    need = [
        "/api/v1/chat/message",
        "/api/v1/chat/prompts",
        "/api/v1/chat/history/{session_id}",
    ]
    return all(p in paths for p in need)


def _prompt_chips_shape() -> bool:
    c = _client()
    r = c.get("/api/v1/chat/prompts")
    if r.status_code != 200:
        return False
    body = r.json()
    if body.get("success") is not True:
        return False
    chips = body.get("data")
    if not isinstance(chips, list) or len(chips) < 2:
        return False
    for chip in chips[:5]:
        if not isinstance(chip, dict):
            return False
        if not chip.get("id") or not chip.get("label") or not chip.get("prompt"):
            return False
    return True


def _chat_message_roundtrip_persists() -> bool:
    c = _client()
    msg = "Explain mutual fund expense ratio fees."
    r = c.post("/api/v1/chat/message", json={"message": msg})
    if r.status_code != 200:
        return False
    body = r.json()
    if body.get("success") is not True:
        return False
    data = body.get("data") or {}
    session_id = data.get("session_id")
    assistant_message = data.get("assistant_message")
    if not session_id or not assistant_message or not isinstance(assistant_message, str):
        return False

    hist = c.get(f"/api/v1/chat/history/{session_id}")
    if hist.status_code != 200:
        return False
    hbody = hist.json()
    if hbody.get("success") is not True:
        return False
    messages = hbody.get("data") or []
    if not isinstance(messages, list) or len(messages) < 2:
        return False

    # Last message should be assistant.
    last = messages[-1]
    return isinstance(last, dict) and last.get("role") == "assistant" and session_id == last.get("session_id")


def run_phase3_evals() -> Phase3EvalReport:
    # Force stable offline behavior: no Supabase network.
    with patch(
        "app.integrations.supabase.client.check_supabase_connectivity",
        new=AsyncMock(return_value=(True, "ok")),
    ):
        checks: list[Check] = [
            Check("openapi_chat_paths", 45.0, _openapi_has_chat_paths),
            Check("prompt_chips_shape", 25.0, _prompt_chips_shape),
            Check("chat_message_roundtrip", 30.0, _chat_message_roundtrip_persists),
        ]

        earned = 0.0
        total = 0.0
        rows: list[dict[str, object]] = []
        for chk in checks:
            total += chk.weight
            ok = False
            try:
                ok = bool(chk.fn())
            except Exception:
                ok = False
            if ok:
                earned += chk.weight
            rows.append({"id": chk.id, "weight": chk.weight, "passed": ok})

        score = round((earned / total) * 100.0, 2) if total else 0.0
        return Phase3EvalReport(
            total_weight=total,
            earned_weight=earned,
            score=score,
            checks=rows,
        )

