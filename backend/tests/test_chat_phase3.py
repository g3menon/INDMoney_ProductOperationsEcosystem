from __future__ import annotations


def test_chat_prompts_and_roundtrip(client):
    prompts = client.get("/api/v1/chat/prompts")
    assert prompts.status_code == 200
    pbody = prompts.json()
    assert pbody["success"] is True
    chips = pbody.get("data")
    assert isinstance(chips, list)
    assert len(chips) >= 2

    msg = "Explain mutual fund expense ratio fees."
    r = client.post("/api/v1/chat/message", json={"message": msg})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True

    data = body.get("data") or {}
    session_id = data.get("session_id")
    assistant_message = data.get("assistant_message")
    assert isinstance(session_id, str) and session_id.startswith("CS-")
    assert isinstance(assistant_message, str) and len(assistant_message) > 0

    hist = client.get(f"/api/v1/chat/history/{session_id}")
    assert hist.status_code == 200
    hbody = hist.json()
    assert hbody["success"] is True
    messages = hbody.get("data") or []
    assert isinstance(messages, list)
    assert len(messages) >= 2
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["session_id"] == session_id

