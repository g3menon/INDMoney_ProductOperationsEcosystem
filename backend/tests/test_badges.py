from __future__ import annotations


def test_badges_shape(client):
    r = client.get("/api/v1/dashboard/badges")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert "customer" in data and "product" in data and "advisor" in data
    assert isinstance(data["supabase_connected"], bool)
