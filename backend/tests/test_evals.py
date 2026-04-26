from __future__ import annotations


def test_post_evals_phase1(client):
    r = client.post("/api/v1/evals/run", json={"suite": "phase1"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert float(data["score"]) >= 85.0
    assert data["version"] == "phase1-v1"
