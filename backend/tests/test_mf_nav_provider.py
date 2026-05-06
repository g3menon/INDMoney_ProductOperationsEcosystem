from __future__ import annotations

import pytest

from app.integrations.mf_nav_provider import (
    AMFI_NAV_URL,
    MFNavLookupResult,
    find_latest_nav_in_amfi_text,
    lookup_latest_nav,
    nav_lookup_candidate_names,
)
from app.rag.mf_extractor import extract_from_html
from app.rag.answer import compose_structured_answer
from app.schemas.rag import MFFundMetrics
from app.services.customer_router_service import _try_live_nav_enrichment


def test_amfi_nav_parser_prefers_direct_growth_scheme() -> None:
    nav_text = "\n".join(
        [
            "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date",
            "100001;-;-;Motilal Oswal Midcap Fund - Regular Plan - Growth;99.0000;25-Apr-2025",
            "100002;-;-;Motilal Oswal Midcap Fund - Direct Plan - Growth;123.4567;25-Apr-2025",
        ]
    )

    result = find_latest_nav_in_amfi_text(
        fund_name="Motilal Oswal Midcap Fund Direct Growth",
        nav_text=nav_text,
    )

    assert result is not None
    assert result.scheme_code == "100002"
    assert result.nav == 123.4567
    assert result.nav_date == "2025-04-25"


def test_nav_lookup_adds_hdfc_equity_alias_for_flexi_cap_label() -> None:
    names = nav_lookup_candidate_names("HDFC Flexi Cap Direct Plan Growth")
    assert "HDFC Flexi Cap Direct Plan Growth" in names
    assert any("Equity Fund" in n for n in names)


def test_amfi_row_named_hdfc_equity_matches_via_alias_query() -> None:
    """AMFI often keeps legacy ``HDFC Equity Fund`` wording for the flexi-cap scheme."""
    nav_text = "\n".join(
        [
            "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date",
            "119551;-;-;HDFC Equity Fund - Direct Plan - Growth;1845.3200;25-Apr-2025",
        ]
    )
    groww_style = find_latest_nav_in_amfi_text(
        fund_name="HDFC Flexi Cap Direct Plan Growth",
        nav_text=nav_text,
    )
    assert groww_style is None
    alias = find_latest_nav_in_amfi_text(
        fund_name="HDFC Equity Fund - Direct Plan - Growth",
        nav_text=nav_text,
    )
    assert alias is not None
    assert alias.nav == 1845.32


@pytest.mark.asyncio
async def test_lookup_latest_nav_falls_back_to_hdfc_equity_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    nav_text = "\n".join(
        [
            "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date",
            "119551;-;-;HDFC Equity Fund - Direct Plan - Growth;1845.3200;25-Apr-2025",
        ]
    )

    async def _fake_fetch() -> str:
        return nav_text

    monkeypatch.setattr(
        "app.integrations.mf_nav_provider._fetch_amfi_nav_text",
        _fake_fetch,
    )
    result = await lookup_latest_nav("HDFC Flexi Cap Direct Plan Growth")
    assert result is not None
    assert result.scheme_code == "119551"
    assert result.nav == 1845.32


@pytest.mark.asyncio
async def test_nav_enrichment_uses_http_provider_without_playwright(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_lookup(_fund_name: str) -> MFNavLookupResult:
        return MFNavLookupResult(
            scheme_code="100002",
            scheme_name="Motilal Oswal Midcap Fund - Direct Plan - Growth",
            nav=123.4567,
            nav_date="2026-05-05",
        )

    monkeypatch.setattr("app.integrations.mf_nav_provider.lookup_latest_nav", fake_lookup)
    metrics = MFFundMetrics(
        doc_id="motilal-midcap-direct",
        fund_name="Motilal Oswal Midcap Fund Direct Growth",
        source_url="https://groww.in/mutual-funds/motilal-oswal-most-focused-midcap-30-fund-direct-growth",
        scraped_at="2026-05-06T00:00:00Z",
        last_checked="2026-05-06",
    )

    enriched, citation = await _try_live_nav_enrichment(metrics)
    answer = compose_structured_answer(
        "What is the NAV of Motilal Oswal Midcap Fund?",
        enriched,
        "direct_metric_query",
    ).answer

    assert citation is not None
    assert citation.source_url == AMFI_NAV_URL
    assert "NAV: \u20b9123.46 as of 2026-05-05" in answer
    assert AMFI_NAV_URL in answer
    assert "Playwright" not in answer
    assert "requires live page data" not in answer


def test_unavailable_nav_copy_does_not_recommend_playwright() -> None:
    metrics = MFFundMetrics(
        doc_id="motilal-midcap-direct",
        fund_name="Motilal Oswal Midcap Fund Direct Growth",
        source_url="https://groww.in/mutual-funds/motilal-oswal-most-focused-midcap-30-fund-direct-growth",
        scraped_at="2026-05-06T00:00:00Z",
        last_checked="2026-05-06",
    )

    answer = compose_structured_answer(
        "What is the NAV of Motilal Oswal Midcap Fund?",
        metrics,
        "direct_metric_query",
    ).answer

    assert "NAV data is currently being updated" in answer
    assert "groww.in" in answer
    assert "Playwright" not in answer
    assert "requires live page data" not in answer


def test_groww_page_sections_are_extracted_from_mutual_fund_text() -> None:
    text = """
Motilal Oswal Midcap Fund Direct Growth
Equity
Mid Cap
Very High Risk
NAV: 05 May '26
₹105.24
Min. for SIP
₹500
Fund size (AUM)
₹31,046.66 Cr
Expense ratio
0.75%
Rating
3
Return calculator
1 year₹60,000₹56,670
-5.55%
3 years₹1,80,000₹1,96,836
+9.35%
5 years₹3,00,000₹4,50,078
+50.03%
10 years₹6,00,000₹16,51,993
+175.33%
Holdings (2)
Name Sector Instruments Assets
Kalyan Jewellers India Ltd. Consumer Discretionary Equity 7.44%
One97 Communications Ltd. Services Equity 7.34%
Minimum investments
Min. for 1st investment
₹500
Min. for 2nd investment
₹500
Min. for SIP
₹500
Returns and rankings
Name 3Y 5Y 10Y All
Fund returns+21.9%+24.1%+18.0%+21.3%
Category average ( Equity Mid Cap )+21.6%+21.5%+16.0%--
Rank (Equity Mid Cap)25 1 9--
Fund management
###
AA
Ankit Agarwal
Jan 2026 - Present
View details
Education
Mr. Agarwal has done B. Tech. Computer Science and Engg., Economics Management, PGDM Finance.
Experience
Prior to joining Motilal Oswal Mutual Fund he has worked with UTI Mutual Fund.
Also manages these schemes
Motilal Oswal Focused Fund Direct Growth
About Motilal Oswal Midcap Fund Direct Growth
The fund currently has an Asset Under Management(AUM) of ₹1,24,826 Cr and the Latest NAV as of 05 May 2026 is ₹105.24.
"""

    metrics, report = extract_from_html(
        html="<html><title>Motilal Oswal Midcap Fund Direct Growth</title></html>",
        url="https://groww.in/mutual-funds/motilal-oswal-most-focused-midcap-30-fund-direct-growth",
        doc_id="motilal-midcap-direct",
        normalized_text=text,
    )

    assert metrics.nav == 105.24
    assert metrics.nav_date == "2026-05-05"
    assert metrics.min_sip_amount == 500
    assert metrics.aum_cr == 31046.66
    assert metrics.expense_ratio_pct == 0.75
    assert metrics.rating == "3"
    assert metrics.returns is not None
    assert metrics.returns.ten_year == 175.33
    assert len(metrics.investment_returns) == 4
    assert metrics.top_holdings[0].name == "Kalyan Jewellers India Ltd."
    assert metrics.top_holdings[0].sector == "Consumer Discretionary"
    assert metrics.top_holdings[0].instrument == "Equity"
    assert metrics.returns_and_rankings is not None
    assert metrics.returns_and_rankings.fund_returns["ten_year"] == 18.0
    assert metrics.returns_and_rankings.rank["five_year"] == 1
    assert metrics.fund_managers[0].name == "Ankit Agarwal"
    assert report.tier_used["fund_managers"] == "groww_text"
