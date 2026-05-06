"""MIME shape for Gmail weekly pulse send (single text/html, CRLF via SMTP policy)."""

from __future__ import annotations

import base64

from app.mcp.send_weekly_pulse_email import _make_raw_message


def _b64url_decode(s: str) -> bytes:
    pad = (-len(s)) % 4
    return base64.urlsafe_b64decode(s.encode("ascii") + (b"=" * pad))


def test_raw_message_is_single_html_part() -> None:
    raw_b64 = _make_raw_message(
        to="pm@example.com",
        sender="ops@example.com",
        subject="Weekly Pulse — unit",
        html="<!DOCTYPE html><html><body><p>Hi</p></body></html>",
    )
    decoded = _b64url_decode(raw_b64)
    assert b"\r\n" in decoded
    decoded_s = decoded.decode("utf-8")
    assert "multipart/alternative" not in decoded_s
    assert 'Content-Type: text/html; charset="utf-8"' in decoded_s
    assert decoded.count(b"MIME-Version") == 1

