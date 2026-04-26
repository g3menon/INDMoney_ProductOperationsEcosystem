from __future__ import annotations


def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["status"] in ("ok", "degraded")
    assert body["data"]["correlation_id"]
    assert "settings" in body["data"]


def test_health_no_secret_leak(client):
    blob = str(client.get("/api/v1/health").json())
    assert "test-service-role-key" not in blob
    assert "service_role" not in blob.lower()
