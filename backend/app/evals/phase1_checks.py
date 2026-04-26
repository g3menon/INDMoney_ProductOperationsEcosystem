"""
Phase 1 automated evals: API contract, safe settings exposure, and routing shape.
Target: >= 85% (`Docs/Rules.md` EVAL11 — thresholds documented here).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from fastapi.testclient import TestClient
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class Check:
    id: str
    weight: float
    fn: Callable[[], bool]


class Phase1EvalReport(BaseModel):
    version: str = Field(default="phase1-v1")
    total_weight: float
    earned_weight: float
    score: float
    checks: list[dict[str, object]]


def _app():
    from app.main import app as fastapi_app

    return fastapi_app


def _client() -> TestClient:
    return TestClient(_app(), raise_server_exceptions=True)


def _health_envelope_ok() -> bool:
    c = _client()
    r = c.get("/api/v1/health")
    if r.status_code != 200:
        return False
    body = r.json()
    if body.get("success") is not True:
        return False
    data = body.get("data") or {}
    if data.get("status") not in ("ok", "degraded"):
        return False
    if not data.get("correlation_id"):
        return False
    return True


def _health_has_safe_settings() -> bool:
    c = _client()
    data = (c.get("/api/v1/health").json() or {}).get("data") or {}
    settings = data.get("settings") or {}
    if not isinstance(settings, dict):
        return False
    blob = json.dumps(settings)
    for needle in ("service_role", "SUPABASE_SERVICE_ROLE", "secret", "BEGIN "):
        if needle.lower() in blob.lower():
            return False
    if settings.get("supabase_configured") is not True:
        return False
    return True


def _badges_envelope_ok() -> bool:
    c = _client()
    r = c.get("/api/v1/dashboard/badges")
    if r.status_code != 200:
        return False
    body = r.json()
    if body.get("success") is not True:
        return False
    data = body.get("data") or {}
    for key in ("customer", "product", "advisor"):
        if key not in data:
            return False
    if "supabase_connected" not in data:
        return False
    return True


def _badges_typing_shape() -> bool:
    c = _client()
    data = (c.get("/api/v1/dashboard/badges").json() or {}).get("data") or {}
    cust = data.get("customer") or {}
    prod = data.get("product") or {}
    adv = data.get("advisor") or {}
    try:
        assert isinstance(cust.get("booking_in_progress"), int)
        assert isinstance(prod.get("pulse_ready"), bool)
        assert isinstance(adv.get("pending_approvals"), int)
    except AssertionError:
        return False
    return True


def _supabase_connected_is_boolean() -> bool:
    c = _client()
    data = (c.get("/api/v1/dashboard/badges").json() or {}).get("data") or {}
    return isinstance(data.get("supabase_connected"), bool)


def _openapi_lists_core_paths() -> bool:
    c = _client()
    r = c.get("/openapi.json")
    if r.status_code != 200:
        return False
    spec = r.json()
    paths = spec.get("paths") or {}
    need = ["/api/v1/health", "/api/v1/dashboard/badges", "/api/v1/evals/run"]
    return all(p in paths for p in need)


def _correlation_header_roundtrip() -> bool:
    c = _client()
    r = c.get("/api/v1/health", headers={"X-Correlation-ID": "phase1-test-cid"})
    if r.status_code != 200:
        return False
    if r.headers.get("X-Correlation-ID") != "phase1-test-cid":
        return False
    data = r.json().get("data") or {}
    return data.get("correlation_id") == "phase1-test-cid"


def _root_route_exists() -> bool:
    c = _client()
    r = c.get("/")
    if r.status_code != 200:
        return False
    return "service" in r.json()


def _cors_preflight_headers() -> bool:
    c = _client()
    r = c.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    return r.status_code in (200, 204)


CHECKS: list[Check] = [
    Check("health_envelope", 13.0, _health_envelope_ok),
    Check("health_safe_settings", 13.0, _health_has_safe_settings),
    Check("badges_envelope", 13.0, _badges_envelope_ok),
    Check("badges_shape", 10.0, _badges_typing_shape),
    Check("supabase_flag_boolean", 14.0, _supabase_connected_is_boolean),
    Check("openapi_paths", 10.0, _openapi_lists_core_paths),
    Check("correlation_id", 10.0, _correlation_header_roundtrip),
    Check("root_route", 7.0, _root_route_exists),
    Check("cors_preflight", 10.0, _cors_preflight_headers),
]


def run_phase1_evals() -> Phase1EvalReport:
    rows: list[dict[str, object]] = []
    earned = 0.0
    total = 0.0
    for chk in CHECKS:
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
    return Phase1EvalReport(
        total_weight=total,
        earned_weight=earned,
        score=score,
        checks=rows,
    )
