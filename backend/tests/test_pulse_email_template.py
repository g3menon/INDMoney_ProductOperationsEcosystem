"""Weekly pulse email rendering (HTML + plain)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.mcp.pulse_email_template import build_pulse_email_parts
from app.schemas.pulse import PulseMetrics, PulseQuote, PulseTheme, WeeklyPulse


def test_build_pulse_escapes_markup_in_payload() -> None:
    pulse = WeeklyPulse(
        pulse_id="PULSE-TEST-XSS-001",
        created_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        metrics=PulseMetrics(reviews_considered=10, average_rating=3.5, lookback_weeks=8),
        themes=[
            PulseTheme(theme="Fees & charges", summary="Users ask about <hidden>", count=3),
            PulseTheme(theme="Trust", summary="Verification", count=2),
        ],
        quotes=[
            PulseQuote(review_id="rid-1", quote='Say "hello" & <pricing>', rating=4),
        ],
        recommended_actions=["Fix <pricing> wording."],
        narrative="<style>evil</style>Summary line.",
        degraded=True,
        degraded_reason="low_review_volume:90",
    )
    subject, plain, html = build_pulse_email_parts(pulse)
    assert "PULSE-TEST-XSS-001" in subject
    assert "<style>" not in html
    assert "&lt;style&gt;" in html or "&lt;/style&gt;" in html
    assert "<pricing>" not in html
    assert "<hidden>" not in html
    assert "Weekly Pulse" in html
    assert "Voice of customer" in html
    assert "&lt;pricing&gt;" in plain or "&amp;" in plain
    assert "Themes:" in plain


def test_build_pulse_empty_state() -> None:
    subject, plain, html = build_pulse_email_parts(None)
    assert "not available" in subject.lower()
    assert "Weekly Pulse" in html
    assert "generate" in plain.lower()
