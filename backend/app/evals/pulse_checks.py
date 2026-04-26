"""
Phase 2 automated evals: Weekly Pulse API + Product-tab prerequisites.
Target: >= 85% (see `Docs/Rules.md` EVAL11).
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


class Phase2EvalReport(BaseModel):
    version: str = Field(default="phase2-v1")
    total_weight: float
    earned_weight: float
    score: float
    checks: list[dict[str, object]]


def _app():
    from app.main import app as fastapi_app

    return fastapi_app


def _client() -> TestClient:
    return TestClient(_app(), raise_server_exceptions=True)


def _pulse_generate_fixture_ok() -> bool:
    c = _client()
    r = c.post("/api/v1/pulse/generate", json={"use_fixture": True, "lookback_weeks": 8})
    if r.status_code != 200:
        return False
    body = r.json()
    if body.get("success") is not True:
        return False
    data = body.get("data") or {}
    return bool(data.get("pulse_id")) and (data.get("metrics") or {}).get("reviews_considered", 0) >= 1


def _pulse_current_returns_object_or_null() -> bool:
    c = _client()
    r = c.get("/api/v1/pulse/current")
    if r.status_code != 200:
        return False
    body = r.json()
    return body.get("success") is True and ("data" in body)


def _pulse_history_list_shape() -> bool:
    c = _client()
    r = c.get("/api/v1/pulse/history?limit=5")
    if r.status_code != 200:
        return False
    body = r.json()
    if body.get("success") is not True:
        return False
    data = body.get("data")
    return isinstance(data, list)


def _subscribe_unsubscribe_roundtrip() -> bool:
    c = _client()
    sub = c.post("/api/v1/pulse/subscribe", json={"email": "pm@example.com"})
    if sub.status_code != 200:
        return False
    if sub.json().get("data", {}).get("status") != "subscribed":
        return False
    unsub = c.post("/api/v1/pulse/unsubscribe", json={"email": "pm@example.com"})
    if unsub.status_code != 200:
        return False
    return unsub.json().get("data", {}).get("status") == "unsubscribed"


def _openapi_has_pulse_paths() -> bool:
    c = _client()
    spec = c.get("/openapi.json").json()
    paths = spec.get("paths") or {}
    need = [
        "/api/v1/pulse/generate",
        "/api/v1/pulse/current",
        "/api/v1/pulse/history",
        "/api/v1/pulse/subscribe",
        "/api/v1/pulse/unsubscribe",
    ]
    return all(p in paths for p in need)


def run_phase2_evals() -> Phase2EvalReport:
    # Force stable offline behavior: no Supabase network.
    with patch(
        "app.integrations.supabase.client.check_supabase_connectivity",
        new=AsyncMock(return_value=(True, "ok")),
    ):
        checks: list[Check] = [
            Check("pulse_generate_fixture", 35.0, _pulse_generate_fixture_ok),
            Check("pulse_current", 10.0, _pulse_current_returns_object_or_null),
            Check("pulse_history", 10.0, _pulse_history_list_shape),
            Check("subscribe_unsubscribe", 25.0, _subscribe_unsubscribe_roundtrip),
            Check("openapi_pulse_paths", 20.0, _openapi_has_pulse_paths),
        ]

        rows: list[dict[str, object]] = []
        earned = 0.0
        total = 0.0
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
        return Phase2EvalReport(
            total_weight=total,
            earned_weight=earned,
            score=score,
            checks=rows,
        )
