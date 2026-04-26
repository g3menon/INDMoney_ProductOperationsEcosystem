"""Pytest fixtures: env, Supabase ping mock, settings cache reset."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _test_env() -> None:
    os.environ["APP_ENV"] = "test"
    os.environ["LOG_LEVEL"] = "warning"
    os.environ["FRONTEND_BASE_URL"] = "http://localhost:3000"
    os.environ["SUPABASE_URL"] = "https://example.supabase.co"
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-service-role-key"
    os.environ["PHASE1_SKIP_SUPABASE_STARTUP_CHECK"] = "true"
    from app.core.config import clear_settings_cache

    clear_settings_cache()
    yield


@pytest.fixture(autouse=True)
def _mock_supabase_ping(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_ok(_settings):
        return True, "ok"

    monkeypatch.setattr(
        "app.integrations.supabase.client.check_supabase_connectivity",
        _fake_ok,
    )


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c
