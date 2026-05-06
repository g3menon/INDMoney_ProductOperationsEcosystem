from app.rag.public_messages import NAV_UNAVAILABLE_FOR_USER
from app.rag.response_sanitize import sanitize_mf_assistant_text


def test_sanitize_replaces_playwright_nav_line() -> None:
    raw = (
        "**HDFC Flexi Cap Direct Plan Growth**\n"
        "NAV: not yet available (live data requires JS rendering — run mf_extractor with Playwright)\n"
        "Source: https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth\n"
    )
    out = sanitize_mf_assistant_text(raw)
    assert "Playwright" not in out
    assert "mf_extractor" not in out
    assert NAV_UNAVAILABLE_FOR_USER in out
    assert "HDFC Flexi Cap" in out
