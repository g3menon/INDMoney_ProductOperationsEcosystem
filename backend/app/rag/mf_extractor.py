"""Phase 4: Structured mutual-fund metrics extractor for Groww MF pages.

Extraction strategy (four tiers, applied in order, results merged):
  Tier 1 — URL slug  : derives plan, option, initial fund_name (always works).
  Tier 2 — __NEXT_DATA__ JSON : Next.js SSR page props; may contain category,
            AMC, risk, benchmark, minimums, expense ratio.
  Tier 3 — BeautifulSoup HTML : structured selectors for visible page sections;
            supplements Tier 2 for fields not in SSR props.
  Tier 4 — Regex on normalized text : reliable fallback for fields present as
            narrative prose (expense ratio, exit load, category, risk, minimums).

Optional **Playwright** (see ``fetch_groww_fund_page_html_playwright`` and
``enrich_metrics_with_playwright``): loads the live page so client-rendered
blocks (NAV, AUM, returns tables, holdings, sector mix) can be extracted when
static HTTP HTML is a shell.

Fields absent from a given HTML snapshot are set to None and summarized ONCE
via ExtractionReport.log_summary().
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.schemas.rag import (
    MFFundManager,
    MFFundMetrics,
    MFHolding,
    MFInvestmentReturn,
    MFReturns,
    MFReturnsAndRankings,
    MFSectorAlloc,
)

logger = logging.getLogger(__name__)

# Fields that are often absent from the static/indexed HTML snapshot.
_SNAPSHOT_OPTIONAL_FIELDS: frozenset[str] = frozenset(
    [
        "nav",
        "nav_date",
        "aum_cr",
        "rating",
        "returns",
        "investment_returns",
        "returns_and_rankings",
        "top_holdings",
        "advanced_ratios",
        "fund_managers",
        "sector_allocation",
        "asset_allocation",
    ]
)

# AMC name inference from fund name tokens.
_AMC_HINTS: list[tuple[str, str]] = [
    ("motilal oswal", "Motilal Oswal AMC"),
    ("hdfc", "HDFC AMC"),
    ("sbi", "SBI Funds Management"),
    ("icici prudential", "ICICI Prudential AMC"),
    ("axis", "Axis AMC"),
    ("kotak", "Kotak Mahindra AMC"),
    ("mirae asset", "Mirae Asset Investment Managers"),
    ("nippon", "Nippon India AMC"),
    ("dsp", "DSP Investment Managers"),
    ("aditya birla", "Aditya Birla Sun Life AMC"),
    ("uti", "UTI AMC"),
    ("franklin", "Franklin Templeton"),
    ("tata", "Tata Asset Management"),
    ("invesco", "Invesco Asset Management"),
    ("quant", "Quant Money Managers"),
    ("parag parikh", "PPFAS Mutual Fund"),
    ("whiteoak", "WhiteOak Capital AMC"),
    ("bandhan", "Bandhan AMC"),
    ("canara robeco", "Canara Robeco AMC"),
    ("sundaram", "Sundaram Asset Management"),
]


# ---------------------------------------------------------------------------
# Extraction report
# ---------------------------------------------------------------------------


@dataclass
class ExtractionReport:
    """Records which fields were extracted from which tier, and which are missing."""

    doc_id: str
    fields_extracted: list[str] = field(default_factory=list)
    fields_missing: list[str] = field(default_factory=list)
    tier_used: dict[str, str] = field(default_factory=dict)
    snapshot_missing: list[str] = field(default_factory=list)

    def record(self, fname: str, tier: str) -> None:
        if fname not in self.fields_extracted:
            self.fields_extracted.append(fname)
        self.tier_used[fname] = tier
        if fname in self.fields_missing:
            self.fields_missing.remove(fname)
        if fname in self.snapshot_missing:
            self.snapshot_missing.remove(fname)

    @property
    def js_only_missing(self) -> list[str]:
        """Backward-compatible alias for older scripts/tests."""
        return self.snapshot_missing

    def missing(self, fname: str, snapshot_optional: bool = False) -> None:
        if fname not in self.fields_missing:
            self.fields_missing.append(fname)
        if snapshot_optional and fname not in self.snapshot_missing:
            self.snapshot_missing.append(fname)

    def log_summary(self) -> None:
        if self.snapshot_missing:
            logger.warning(
                "mf_extractor_snapshot_fields_missing",
                extra={
                    "doc_id": self.doc_id,
                    "fields_unavailable": self.snapshot_missing,
                    "reason": (
                        "not present in indexed HTML snapshot; use approved "
                        "HTTP sources or fixture refresh for enrichment"
                    ),
                },
            )
        non_js_missing = [
            f for f in self.fields_missing if f not in self.snapshot_missing
        ]
        if non_js_missing:
            logger.info(
                "mf_extractor_fields_not_found",
                extra={"doc_id": self.doc_id, "fields": non_js_missing},
            )
        logger.info(
            "mf_extractor_done",
            extra={
                "doc_id": self.doc_id,
                "extracted": len(self.fields_extracted),
                "missing_total": len(self.fields_missing),
                "tiers_used": sorted(set(self.tier_used.values())),
            },
        )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def extract_from_html(
    html: str,
    url: str,
    doc_id: str,
    normalized_text: str = "",
) -> tuple[MFFundMetrics, ExtractionReport]:
    """Extract structured MF metrics from a Groww fund page.

    Args:
        html: Raw page HTML fetched through the HTTP-only source fetcher.
        url: Canonical source URL.
        doc_id: Stable document identifier (e.g. slug[:40]).
        normalized_text: Pre-cleaned text from ``ingest.normalize_document_content``.
            Used as Tier 4 regex fallback.

    Returns:
        Tuple of (MFFundMetrics, ExtractionReport). Fields unavailable from the
        current HTML snapshot are None; ExtractionReport.log_summary() emits one
        consolidated warning for snapshot-only gaps.
    """
    from datetime import datetime, timezone

    report = ExtractionReport(doc_id=doc_id)
    ctx: dict[str, Any] = {}

    _extract_from_url(url, ctx, report)
    _extract_from_next_data(html, ctx, report)
    _extract_from_html_structure(html, ctx, report)
    if normalized_text:
        _extract_from_text_regex(normalized_text, ctx, report)
    _infer_amc(ctx, report)

    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    metrics = MFFundMetrics(
        doc_id=doc_id,
        fund_name=ctx.get("fund_name") or _slug_to_title(url),
        amc=ctx.get("amc"),
        category=ctx.get("category"),
        sub_category=ctx.get("sub_category"),
        plan=ctx.get("plan"),
        option=ctx.get("option"),
        nav=ctx.get("nav"),
        nav_date=ctx.get("nav_date"),
        aum_cr=ctx.get("aum_cr"),
        expense_ratio_pct=ctx.get("expense_ratio_pct"),
        exit_load_pct=ctx.get("exit_load_pct"),
        exit_load_window_days=ctx.get("exit_load_window_days"),
        exit_load_description=ctx.get("exit_load_description"),
        risk_level=ctx.get("risk_level"),
        rating=ctx.get("rating"),
        benchmark=ctx.get("benchmark"),
        min_sip_amount=ctx.get("min_sip_amount"),
        min_lumpsum_amount=ctx.get("min_lumpsum_amount"),
        returns=ctx.get("returns"),
        investment_returns=ctx.get("investment_returns") or [],
        top_holdings=ctx.get("top_holdings") or [],
        advanced_ratios=ctx.get("advanced_ratios") or {},
        returns_and_rankings=ctx.get("returns_and_rankings"),
        fund_managers=ctx.get("fund_managers") or [],
        sector_allocation=ctx.get("sector_allocation") or [],
        asset_allocation=ctx.get("asset_allocation") or {},
        fund_objective=ctx.get("fund_objective"),
        source_url=url,
        scraped_at=scraped_at,
        last_checked=scraped_at[:10],
    )

    # Mark snapshot-optional fields as missing once.
    for fname in _SNAPSHOT_OPTIONAL_FIELDS:
        val = getattr(metrics, fname, None)
        if not val:
            report.missing(fname, snapshot_optional=True)

    report.log_summary()
    return metrics, report


# ---------------------------------------------------------------------------
# Playwright: client-rendered Groww pages
# ---------------------------------------------------------------------------


async def fetch_groww_fund_page_html_playwright(url: str, *, headless: bool = True) -> str | None:
    """Load ``url`` in Chromium and return final HTML after client render.

    Requires ``playwright`` and browser binaries (``playwright install chromium``).
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning(
            "playwright_import_failed",
            extra={"hint": "pip install playwright && playwright install chromium"},
        )
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=90_000)
                # Groww MF pages paint NAV/AUM after hydration; wait for a rupee price.
                try:
                    await page.locator("text=/₹\\s*[\\d,]+\\./").first.wait_for(
                        timeout=25_000,
                        state="visible",
                    )
                except Exception:
                    await page.wait_for_timeout(3000)
                else:
                    await page.wait_for_timeout(500)
                return await page.content()
            finally:
                await browser.close()
    except Exception as exc:
        logger.warning(
            "playwright_groww_fetch_failed",
            extra={"url": url[:120], "error": str(exc)[:200]},
        )
        return None


def _value_empty_for_merge(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and not val.strip():
        return True
    if isinstance(val, (list, tuple)) and len(val) == 0:
        return True
    if isinstance(val, dict) and len(val) == 0:
        return True
    if hasattr(val, "model_dump"):
        nested = val.model_dump()
        if isinstance(nested, dict) and nested:
            return all(_value_empty_for_merge(v) for v in nested.values())
        return True
    return False


def merge_metrics_fill_empty(base: MFFundMetrics, fill: MFFundMetrics) -> MFFundMetrics:
    """Keep ``base`` facts; overlay non-empty values from ``fill`` where base is empty."""
    out = base.model_dump()
    fd = fill.model_dump()
    for name in MFFundMetrics.model_fields:
        if name == "doc_id":
            continue
        if _value_empty_for_merge(getattr(base, name)):
            out[name] = fd[name]
    return MFFundMetrics.model_validate(out)


async def enrich_metrics_with_playwright(metrics: MFFundMetrics) -> MFFundMetrics:
    """Re-fetch the fund page with Playwright and merge newly extracted fields."""
    html = await fetch_groww_fund_page_html_playwright(metrics.source_url)
    if not html:
        return metrics

    from app.rag.ingest import clean_html_content, normalize_document_content

    cleaned = clean_html_content(html)
    normalized = normalize_document_content(cleaned)
    richer, _report = extract_from_html(
        html=html,
        url=metrics.source_url,
        doc_id=metrics.doc_id,
        normalized_text=normalized,
    )
    return merge_metrics_fill_empty(metrics, richer)


def metrics_needs_playwright_enrichment(m: MFFundMetrics) -> bool:
    """True when key fund stats still missing after static HTTP extraction."""
    r = m.returns
    returns_empty = r is None or all(
        getattr(r, name) is None for name in MFReturns.model_fields
    )
    return (
        m.nav is None
        or m.aum_cr is None
        or returns_empty
        or len(m.top_holdings) == 0
        or len(m.sector_allocation) == 0
    )


# ---------------------------------------------------------------------------
# Tier 1: URL slug parsing
# ---------------------------------------------------------------------------


def _slug_to_title(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    return slug.replace("-", " ").title()


def _extract_from_url(url: str, ctx: dict, report: ExtractionReport) -> None:
    slug = url.rstrip("/").split("/")[-1].lower()
    parts = set(slug.split("-"))

    if "direct" in parts:
        _try_set(ctx, report, "plan", "Direct", "url")
    elif "regular" in parts:
        _try_set(ctx, report, "plan", "Regular", "url")

    if "growth" in parts:
        _try_set(ctx, report, "option", "Growth", "url")
    elif "idcw" in parts or "dividend" in parts:
        _try_set(ctx, report, "option", "IDCW", "url")


# ---------------------------------------------------------------------------
# Tier 2: __NEXT_DATA__ JSON parsing
# ---------------------------------------------------------------------------

_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _extract_from_next_data(html: str, ctx: dict, report: ExtractionReport) -> None:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return

    pp = _deep_get(data, ["props", "pageProps"]) or {}
    fund_data: dict = (
        _deep_get(pp, ["fundData"])
        or _deep_get(pp, ["schemeDetails"])
        or _deep_get(pp, ["fundDetails"])
        or {}
    )

    _nd_str(ctx, report, "fund_name", fund_data, pp,
            ["schemeName", "fundName"], ["schemeName"])
    _nd_str(ctx, report, "category", fund_data, pp,
            ["category", "schemeCategory"], [])
    _nd_str(ctx, report, "sub_category", fund_data, pp,
            ["subCategory", "schemeType"], [])
    _nd_str(ctx, report, "amc", fund_data, pp,
            ["amcName", "amc"], ["amcName"])
    _nd_str(ctx, report, "risk_level", fund_data, pp,
            ["riskLevel", "riskometer", "risk"], [])
    _nd_str(ctx, report, "benchmark", fund_data, pp,
            ["benchmarkName", "benchmark"], [])
    _nd_str(ctx, report, "nav_date", fund_data, pp,
            ["navDate", "navAsOfDate"], [])
    _nd_str(ctx, report, "exit_load_description", fund_data, pp,
            ["exitLoadDescription", "exitLoadNote"], [])
    _nd_str(ctx, report, "rating", fund_data, pp,
            ["rating", "valueResearchRating", "morningstarRating"], [])
    _nd_str(ctx, report, "fund_objective", fund_data, pp,
            ["schemeObjective", "investmentObjective", "fundObjective"], [])

    _nd_float(ctx, report, "min_sip_amount", fund_data,
              ["minSipAmount", "minimumSipAmount", "sipMinimumAmount"])
    _nd_float(ctx, report, "min_lumpsum_amount", fund_data,
              ["minPurchaseAmount", "minimumPurchaseAmount", "lumpSumMinimumAmount"])
    _nd_float(ctx, report, "nav", fund_data,
              ["nav", "navValue", "currentNav"])
    _nd_float(ctx, report, "aum_cr", fund_data,
              ["aumInCr", "aum", "fundSize"])
    _nd_float(ctx, report, "expense_ratio_pct", fund_data,
              ["ter", "expenseRatio", "totalExpenseRatio"])
    _nd_float(ctx, report, "exit_load_pct", fund_data,
              ["exitLoad", "exitLoadValue"])


def _nd_str(
    ctx: dict,
    report: ExtractionReport,
    key: str,
    fund_data: dict,
    pp: dict,
    fund_keys: list[str],
    pp_keys: list[str],
) -> None:
    for k in fund_keys:
        v = _coerce_str(_deep_get(fund_data, [k]))
        if v:
            _try_set(ctx, report, key, v, "next_data")
            return
    for k in pp_keys:
        v = _coerce_str(_deep_get(pp, [k]))
        if v:
            _try_set(ctx, report, key, v, "next_data")
            return


def _nd_float(
    ctx: dict,
    report: ExtractionReport,
    key: str,
    fund_data: dict,
    keys: list[str],
) -> None:
    for k in keys:
        v = _coerce_float(_deep_get(fund_data, [k]))
        if v is not None:
            _try_set(ctx, report, key, v, "next_data")
            return


# ---------------------------------------------------------------------------
# Tier 3: BeautifulSoup HTML structure parsing
# ---------------------------------------------------------------------------


def _extract_from_html_structure(
    html: str, ctx: dict, report: ExtractionReport
) -> None:
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:
        return
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return

    # Fund name from h1 / title tag.
    if "fund_name" not in ctx:
        h1 = soup.find("h1")
        if h1:
            t = h1.get_text(strip=True)
            if t:
                _try_set(ctx, report, "fund_name", t, "html")
        if "fund_name" not in ctx:
            title_tag = soup.find("title")
            if title_tag:
                t = title_tag.get_text(strip=True).split("|")[0].split("-")[0].strip()
                if len(t) > 10:
                    _try_set(ctx, report, "fund_name", t, "html")

    # data-testid attribute scanning — Groww uses these in some versions.
    for tag in soup.find_all(attrs={"data-testid": True}):
        testid = (tag.get("data-testid") or "").lower()
        text = tag.get_text(strip=True)
        if not text:
            continue
        if "category" in testid:
            _try_set(ctx, report, "category", text, "html")
        elif "risk" in testid:
            _try_set(ctx, report, "risk_level", text, "html")
        elif "benchmark" in testid:
            _try_set(ctx, report, "benchmark", text, "html")
        elif "expense" in testid or "ter" in testid:
            v = _parse_pct(text)
            if v is not None:
                _try_set(ctx, report, "expense_ratio_pct", v, "html")
        elif "exit" in testid and "load" in testid:
            v = _parse_pct(text)
            if v is not None:
                _try_set(ctx, report, "exit_load_pct", v, "html")
        elif "amc" in testid or "fund-house" in testid:
            _try_set(ctx, report, "amc", text, "html")
        elif "sip" in testid and ("min" in testid or "amount" in testid):
            v = _parse_amount(text)
            if v is not None:
                _try_set(ctx, report, "min_sip_amount", v, "html")
        elif "lump" in testid and ("min" in testid or "amount" in testid):
            v = _parse_amount(text)
            if v is not None:
                _try_set(ctx, report, "min_lumpsum_amount", v, "html")

    # NAV — look for elements with "nav" in class or text near ₹ signs.
    if "nav" not in ctx:
        for tag in soup.find_all(class_=re.compile(r"\bnav\b", re.I)):
            text = tag.get_text(strip=True)
            v = _coerce_float(
                re.search(r"(\d{1,4}\.\d{2,4})", text.replace(",", ""))
            )
            if v and v > 1:
                _try_set(ctx, report, "nav", v, "html")
                break


# ---------------------------------------------------------------------------
# Tier 4: Regex on normalized text
# ---------------------------------------------------------------------------

_RE_CATEGORY = re.compile(r"Category\s*:\s*([^\.\n]+)", re.I)
_RE_SUBCATEGORY = re.compile(r"Sub-?category\s*:\s*([^\.\n]+)", re.I)
_RE_RISK = re.compile(r"Risk\s+Level\s*:\s*([^\.\n]+)", re.I)
_RE_TER = re.compile(
    r"(?:total\s+)?expense\s+ratio.*?(?:TER.*?)?(\d+\.?\d*)\s*%\s*per\s*ann",
    re.I | re.DOTALL,
)
_RE_TER_ALT = re.compile(r"(?:TER|expense\s+ratio)[^%]*?(\d+\.?\d*)\s*%", re.I)
_RE_EXIT_LOAD_PCT = re.compile(r"exit\s+load\s+of\s+(\d+\.?\d*)\s*%", re.I)
_RE_EXIT_LOAD_WINDOW = re.compile(r"within\s+(\d+)\s*(day|year|month)", re.I)
_RE_MIN_INVEST = re.compile(
    r"(?:Minimum Investment|Rs\.?)\s*[:\s]*Rs\.?\s*(\d[\d,]*)\s*(?:for\s+)?(lump\s*sum|SIP)",
    re.I,
)
_RE_MIN_SIP = re.compile(
    r"Rs\.?\s*(\d[\d,]*)\s*(?:for\s+)?(?:SIP|Systematic Investment Plan|monthly SIP)",
    re.I,
)
_RE_MIN_LUMP = re.compile(
    r"Rs\.?\s*(\d[\d,]*)\s*(?:for\s+)?(?:lump\s*sum|lumpsum|one[\s-]time|purchase)",
    re.I,
)
_RE_BENCHMARK = re.compile(
    r"(?:tracks?\s+the|benchmark(?:ed)?\s+(?:against|to)?)\s+"
    r"([A-Z][A-Za-z0-9 &\-]+(?:Index|TRI|TR|Sensex))",
    re.I,
)
_RE_NAV_TEXT = re.compile(r"NAV\s*(?:of\s+)?Rs\.?\s*(\d+\.\d+)", re.I)
_RE_AUM_TEXT = re.compile(r"AUM\s*(?:of\s+)?Rs\.?\s*(\d[\d,.]+)\s*(?:crore|cr)", re.I)


def _extract_from_text_regex(
    text: str, ctx: dict, report: ExtractionReport
) -> None:
    if "category" not in ctx:
        m = _RE_CATEGORY.search(text)
        if m:
            _try_set(ctx, report, "category", m.group(1).strip(), "text_regex")

    if "sub_category" not in ctx:
        m = _RE_SUBCATEGORY.search(text)
        if m:
            _try_set(ctx, report, "sub_category", m.group(1).strip(), "text_regex")

    if "risk_level" not in ctx:
        m = _RE_RISK.search(text)
        if m:
            _try_set(ctx, report, "risk_level", m.group(1).strip(), "text_regex")

    if "expense_ratio_pct" not in ctx:
        m = _RE_TER.search(text) or _RE_TER_ALT.search(text)
        if m:
            v = _coerce_float(m.group(1))
            if v is not None and 0 < v < 5:
                _try_set(ctx, report, "expense_ratio_pct", v, "text_regex")

    if "exit_load_pct" not in ctx:
        m = _RE_EXIT_LOAD_PCT.search(text)
        if m:
            v = _coerce_float(m.group(1))
            if v is not None:
                _try_set(ctx, report, "exit_load_pct", v, "text_regex")

    if "exit_load_window_days" not in ctx:
        m = _RE_EXIT_LOAD_WINDOW.search(text)
        if m:
            n = int(m.group(1))
            unit = m.group(2).lower()
            if "year" in unit:
                n *= 365
            elif "month" in unit:
                n *= 30
            _try_set(ctx, report, "exit_load_window_days", n, "text_regex")

    if "exit_load_description" not in ctx:
        idx = text.lower().find("exit load")
        if idx >= 0:
            snippet = text[idx : idx + 220].split("\n")[0].strip()
            if len(snippet) > 20:
                _try_set(ctx, report, "exit_load_description", snippet, "text_regex")

    # Min SIP / lump sum: try structured "Minimum Investment: Rs X for SIP/lump" first.
    if "min_sip_amount" not in ctx or "min_lumpsum_amount" not in ctx:
        for m in _RE_MIN_INVEST.finditer(text):
            amt = _coerce_float(m.group(1).replace(",", ""))
            label = m.group(2).lower()
            if "sip" in label:
                _try_set(ctx, report, "min_sip_amount", amt, "text_regex")
            else:
                _try_set(ctx, report, "min_lumpsum_amount", amt, "text_regex")

    if "min_sip_amount" not in ctx:
        m = _RE_MIN_SIP.search(text)
        if m:
            _try_set(
                ctx, report, "min_sip_amount",
                _coerce_float(m.group(1).replace(",", "")), "text_regex",
            )

    if "min_lumpsum_amount" not in ctx:
        m = _RE_MIN_LUMP.search(text)
        if m:
            _try_set(
                ctx, report, "min_lumpsum_amount",
                _coerce_float(m.group(1).replace(",", "")), "text_regex",
            )

    if "benchmark" not in ctx:
        m = _RE_BENCHMARK.search(text)
        if m:
            _try_set(ctx, report, "benchmark", m.group(1).strip(), "text_regex")

    if "nav" not in ctx:
        m = _RE_NAV_TEXT.search(text)
        if m:
            v = _coerce_float(m.group(1))
            if v and v > 1:
                _try_set(ctx, report, "nav", v, "text_regex")

    if "aum_cr" not in ctx:
        m = _RE_AUM_TEXT.search(text)
        if m:
            v = _coerce_float(m.group(1).replace(",", ""))
            if v:
                _try_set(ctx, report, "aum_cr", v, "text_regex")

    if "fund_objective" not in ctx:
        paras = [p.strip() for p in text.split("\n") if len(p.strip()) > 60]
        if paras:
            _try_set(ctx, report, "fund_objective", paras[0][:400], "text_regex")

    if "fund_name" not in ctx:
        lines = [ln.strip() for ln in text.split("\n") if len(ln.strip()) > 20]
        if lines:
            _try_set(ctx, report, "fund_name", lines[0][:120], "text_regex")

    _extract_groww_page_sections(text, ctx, report)


# ---------------------------------------------------------------------------
# Groww page section parsing from normalized text
# ---------------------------------------------------------------------------

_PERIOD_KEYS = {
    "1": "one_year",
    "3": "three_year",
    "5": "five_year",
    "10": "ten_year",
    "all": "all_time",
}
_RETURN_CALC_RE = re.compile(
    r"\b(1|3|5|10)\s+years?\s*₹\s*([\d,]+(?:\.\d+)?)\s*₹\s*([\d,]+(?:\.\d+)?)"
    r"\s*([+-]?\d+(?:\.\d+)?)\s*%",
    re.I,
)
_NAV_LABEL_RE = re.compile(
    r"NAV:\s*([0-9]{1,2}\s+[A-Za-z]{3}\s+'?[0-9]{2,4})\s*₹\s*([\d,.]+)",
    re.I,
)
_LATEST_NAV_RE = re.compile(
    r"Latest\s+NAV\s+as\s+of\s+([0-9]{1,2}\s+[A-Za-z]{3}\s+[0-9]{4})\s+is\s+₹\s*([\d,.]+)",
    re.I,
)
_AUM_RE = re.compile(
    r"(?:Fund\s+size\s*\(AUM\)|Asset\s+Under\s+Management\s*\(AUM\))"
    r"(?:\s+of)?\s*₹\s*([\d,.]+)\s*Cr",
    re.I,
)
_SIP_RE = re.compile(r"Minimum\s+SIP\s+Investment\s+is\s+set\s+to\s+₹\s*([\d,.]+)", re.I)
_LUMPSUM_RE = re.compile(r"Minimum\s+Lumpsum\s+Investment\s+is\s+₹\s*([\d,.]+)", re.I)
_RISK_SENTENCE_RE = re.compile(r"\bis\s+rated\s+([A-Za-z ]+?)\s+risk\b", re.I)
_RANKINGS_RE = re.compile(
    r"Fund returns\s*"
    r"([+-]?\d+(?:\.\d+)?)%\s*([+-]?\d+(?:\.\d+)?)%\s*"
    r"([+-]?\d+(?:\.\d+)?)%\s*([+-]?\d+(?:\.\d+)?)%\s*"
    r"Category average \([^)]+\)\s*"
    r"([+-]?\d+(?:\.\d+)?)%\s*([+-]?\d+(?:\.\d+)?)%\s*"
    r"([+-]?\d+(?:\.\d+)?)%\s*(--|[+-]?\d+(?:\.\d+)?%)\s*"
    # Groww sometimes omits whitespace before a trailing "--" (e.g. "9--").
    r"Rank \([^)]+\)\s*(\d+|--)\s*(\d+|--)\s*(\d+|--)\s*(\d+|--)",
    re.I,
)
_ADVANCED_RATIO_LABELS = {
    "alpha": "alpha",
    "beta": "beta",
    "sharpe ratio": "sharpe",
    "sharpe": "sharpe",
    "sortino ratio": "sortino",
    "sortino": "sortino",
    "standard deviation": "standard_deviation",
    "std dev": "standard_deviation",
}
_HOLDING_SECTORS = [
    "Consumer Discretionary",
    "Consumer Staples",
    "Services",
    "Technology",
    "Communication",
    "Capital Goods",
    "Financial",
    "Automobile",
    "Construction",
    "Healthcare",
    "Energy",
    "Metals & Mining",
    "Chemicals",
    "Insurance",
    "Materials",
    "Real Estate",
    "Textiles",
    "Utilities",
]
_HOLDING_INSTRUMENTS = ["Equity", "Futures", "Debt", "REIT", "InvIT"]


def _extract_groww_page_sections(
    text: str,
    ctx: dict,
    report: ExtractionReport,
) -> None:
    lines = _clean_lines(text)
    compact = " ".join(lines)

    _extract_groww_snapshot_metrics(lines, compact, ctx, report)
    _extract_groww_investment_returns(compact, ctx, report)
    _extract_groww_returns_and_rankings(compact, ctx, report)
    _extract_groww_holdings(lines, ctx, report)
    _extract_groww_advanced_ratios(lines, ctx, report)
    _extract_groww_fund_managers(lines, ctx, report)


def _clean_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _extract_groww_snapshot_metrics(
    lines: list[str],
    compact: str,
    ctx: dict,
    report: ExtractionReport,
) -> None:
    if "nav" not in ctx:
        m = _NAV_LABEL_RE.search(compact) or _LATEST_NAV_RE.search(compact)
        if m:
            date_s = _parse_groww_date(m.group(1))
            nav = _coerce_float(m.group(2).replace(",", ""))
            if nav and nav > 1:
                _try_set(ctx, report, "nav", nav, "groww_text")
                if date_s:
                    _try_set(ctx, report, "nav_date", date_s, "groww_text")

    if "aum_cr" not in ctx:
        m = _AUM_RE.search(compact)
        if m:
            _try_set(ctx, report, "aum_cr", _coerce_float(m.group(1).replace(",", "")), "groww_text")

    if "expense_ratio_pct" not in ctx:
        expense = _value_after_label(lines, "expense ratio", _parse_pct)
        if expense is not None:
            _try_set(ctx, report, "expense_ratio_pct", expense, "groww_text")

    if "rating" not in ctx:
        rating = _value_after_label(lines, "rating", lambda s: _coerce_float(s))
        if rating is not None:
            _try_set(ctx, report, "rating", str(int(rating)) if float(rating).is_integer() else str(rating), "groww_text")

    if "min_sip_amount" not in ctx:
        sip = _value_after_label(lines, "min. for sip", _parse_amount)
        if sip is None:
            m = _SIP_RE.search(compact)
            sip = _coerce_float(m.group(1).replace(",", "")) if m else None
        if sip is not None:
            _try_set(ctx, report, "min_sip_amount", sip, "groww_text")

    if "min_lumpsum_amount" not in ctx:
        lump = _value_after_label(lines, "min. for 1st investment", _parse_amount)
        if lump is None:
            m = _LUMPSUM_RE.search(compact)
            lump = _coerce_float(m.group(1).replace(",", "")) if m else None
        if lump is not None:
            _try_set(ctx, report, "min_lumpsum_amount", lump, "groww_text")

    if "risk_level" not in ctx:
        m = _RISK_SENTENCE_RE.search(compact)
        if m:
            _try_set(ctx, report, "risk_level", f"{m.group(1).strip()} Risk", "groww_text")


def _investment_period_to_returns_field(period: str) -> str | None:
    """Map Groww return-calculator label to :class:`MFReturns` attribute name."""
    p = period.strip().lower()
    if p == "1 year":
        return "one_year"
    if p == "3 years":
        return "three_year"
    if p == "5 years":
        return "five_year"
    if p == "10 years":
        return "ten_year"
    return None


def _extract_groww_investment_returns(
    compact: str,
    ctx: dict,
    report: ExtractionReport,
) -> None:
    rows: list[MFInvestmentReturn] = []

    for m in _RETURN_CALC_RE.finditer(compact):
        period_num = m.group(1)
        return_pct = _coerce_float(m.group(4))
        rows.append(
            MFInvestmentReturn(
                period=f"{period_num} year" if period_num == "1" else f"{period_num} years",
                total_investment=_coerce_float(m.group(2).replace(",", "")),
                current_value=_coerce_float(m.group(3).replace(",", "")),
                return_pct=return_pct,
            )
        )

    if rows:
        _try_set(ctx, report, "investment_returns", rows, "groww_text")
        # Return calculator shows absolute gain %; ``MFReturns`` holds those here.
        # Annualised table values go into ``returns_and_rankings`` only and may
        # fill ``MFReturns`` slots that the calculator did not (see merge below).
        ret = ctx.get("returns") or MFReturns()
        changed = False
        for row in rows:
            field = _investment_period_to_returns_field(row.period)
            if not field or row.return_pct is None:
                continue
            if getattr(ret, field, None) is None:
                setattr(ret, field, row.return_pct)
                changed = True
        if changed and "returns" not in ctx:
            _try_set(ctx, report, "returns", ret, "groww_text")


def _extract_groww_returns_and_rankings(
    compact: str,
    ctx: dict,
    report: ExtractionReport,
) -> None:
    if "returns_and_rankings" in ctx:
        return
    m = _RANKINGS_RE.search(compact)
    if not m:
        return
    periods = ["three_year", "five_year", "ten_year", "all_time"]
    fund_returns = {
        period: value
        for period, raw in zip(periods, m.group(1, 2, 3, 4))
        if (value := _coerce_float(raw)) is not None
    }
    category_average: dict[str, float] = {}
    for period, raw in zip(periods, m.group(5, 6, 7, 8)):
        if raw == "--":
            continue
        value = _coerce_float(raw.rstrip("%"))
        if value is not None:
            category_average[period] = value
    rank: dict[str, int] = {}
    for period, raw in zip(periods, m.group(9, 10, 11, 12)):
        if raw != "--":
            rank[period] = int(raw)
    _try_set(
        ctx,
        report,
        "returns_and_rankings",
        MFReturnsAndRankings(
            fund_returns=fund_returns,
            category_average=category_average,
            rank=rank,
        ),
        "groww_text",
    )

    returns = ctx.get("returns") or MFReturns()
    changed = False
    for period, value in fund_returns.items():
        if getattr(returns, period, None) is None:
            setattr(returns, period, value)
            changed = True
    if changed and "returns" not in ctx:
        _try_set(ctx, report, "returns", returns, "groww_text")


def _extract_groww_holdings(
    lines: list[str],
    ctx: dict,
    report: ExtractionReport,
) -> None:
    if ctx.get("top_holdings"):
        return
    start = _find_line_idx(lines, lambda ln: "holdings" in ln.lower())
    end = _find_line_idx(lines, lambda ln: "minimum investments" in ln.lower(), start + 1 if start >= 0 else 0)
    if start < 0 or end < 0 or end <= start:
        return
    holdings: list[MFHolding] = []
    for line in lines[start + 1 : end]:
        parsed = _parse_holding_line(line)
        if parsed:
            holdings.append(parsed)
        if len(holdings) >= 25:
            break
    if holdings:
        _try_set(ctx, report, "top_holdings", holdings, "groww_text")


def _parse_holding_line(line: str) -> MFHolding | None:
    if "%" not in line:
        return None
    weight_match = re.search(r"(-?\d+(?:\.\d+)?)\s*%$", line)
    if not weight_match:
        return None
    weight = _coerce_float(weight_match.group(1))
    head = line[: weight_match.start()].strip()
    instrument = None
    for candidate in _HOLDING_INSTRUMENTS:
        if re.search(rf"\b{re.escape(candidate)}\b$", head, re.I):
            instrument = candidate
            head = re.sub(rf"\b{re.escape(candidate)}\b$", "", head, flags=re.I).strip()
            break
    sector = None
    for candidate in sorted(_HOLDING_SECTORS, key=len, reverse=True):
        match = re.search(rf"{re.escape(candidate)}$", head, re.I)
        if match:
            sector = candidate
            name = head[: match.start()].strip(" -")
            break
    else:
        name = head
    if not name or len(name) < 3:
        return None
    return MFHolding(name=name, sector=sector, instrument=instrument, weight_pct=weight)


def _extract_groww_advanced_ratios(
    lines: list[str],
    ctx: dict,
    report: ExtractionReport,
) -> None:
    if ctx.get("advanced_ratios"):
        return
    ratios: dict[str, float] = {}
    lower_lines = [ln.lower() for ln in lines]
    for idx, lower in enumerate(lower_lines):
        key = _ADVANCED_RATIO_LABELS.get(lower)
        if not key:
            continue
        for candidate in lines[idx + 1 : idx + 3]:
            value = _coerce_float(candidate.replace("%", ""))
            if value is not None:
                ratios[key] = value
                break
    if ratios:
        _try_set(ctx, report, "advanced_ratios", ratios, "groww_text")


def _extract_groww_fund_managers(
    lines: list[str],
    ctx: dict,
    report: ExtractionReport,
) -> None:
    if ctx.get("fund_managers"):
        return
    start = _find_line_idx(lines, lambda ln: "fund management" in ln.lower())
    if start < 0:
        return
    end = _find_line_idx(
        lines,
        lambda ln: ln.lower().startswith("about ") or ln.lower() == "fund house",
        start + 1,
    )
    section = lines[start + 1 : end if end > start else min(len(lines), start + 120)]
    managers: list[MFFundManager] = []
    idx = 0
    while idx < len(section):
        if not _looks_like_manager_name(section[idx]):
            idx += 1
            continue
        name = section[idx]
        tenure = section[idx + 1] if idx + 1 < len(section) and _looks_like_tenure(section[idx + 1]) else None
        education = _text_after_marker(section, "Education", idx, stop_markers={"Experience", "Also manages these schemes"})
        experience = _text_after_marker(section, "Experience", idx, stop_markers={"Also manages these schemes"})
        also_manages = _list_after_marker(section, "Also manages these schemes", idx, stop_markers={"###", "Education"})
        managers.append(
            MFFundManager(
                name=name,
                tenure=tenure,
                education=education,
                experience=experience,
                also_manages=also_manages[:12],
            )
        )
        next_card = _find_line_idx(section, lambda ln: ln == "###", idx + 1)
        idx = next_card + 1 if next_card > idx else idx + 2
        if len(managers) >= 8:
            break
    if managers:
        _try_set(ctx, report, "fund_managers", managers, "groww_text")


def _value_after_label(lines: list[str], label: str, parser) -> Any:
    label_l = label.lower()
    for idx, line in enumerate(lines):
        if line.lower() != label_l:
            continue
        for candidate in lines[idx + 1 : idx + 4]:
            parsed = parser(candidate)
            if parsed is not None:
                return parsed
    return None


def _find_line_idx(lines: list[str], predicate, start: int = 0) -> int:
    for idx in range(max(0, start), len(lines)):
        if predicate(lines[idx]):
            return idx
    return -1


def _parse_groww_date(raw: str) -> str | None:
    from datetime import datetime

    cleaned = raw.replace("'", "").strip()
    for fmt in ("%d %b %Y", "%d %b %y"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _looks_like_manager_name(line: str) -> bool:
    if len(line) < 5 or len(line) > 70:
        return False
    lower = line.lower()
    if lower in {"view details", "education", "experience", "also manages these schemes"}:
        return False
    if "fund" in lower or lower.endswith("growth"):
        return False
    if re.fullmatch(r"[A-Z]{1,5}", line):
        return False
    return bool(re.fullmatch(r"[A-Z][A-Za-z.' -]+", line))


def _looks_like_tenure(line: str) -> bool:
    return bool(re.search(r"\b(19|20)\d{2}\b", line) and "present" in line.lower())


def _text_after_marker(
    section: list[str],
    marker: str,
    start: int,
    stop_markers: set[str],
) -> str | None:
    marker_l = marker.lower()
    stop_l = {m.lower() for m in stop_markers}
    marker_idx = _find_line_idx(section, lambda ln: ln.lower() == marker_l, start)
    if marker_idx < 0:
        return None
    parts: list[str] = []
    for line in section[marker_idx + 1 : marker_idx + 5]:
        if line.lower() in stop_l or _looks_like_manager_name(line):
            break
        if line.lower() != "view details":
            parts.append(line)
    text = " ".join(parts).strip()
    return text or None


def _list_after_marker(
    section: list[str],
    marker: str,
    start: int,
    stop_markers: set[str],
) -> list[str]:
    marker_l = marker.lower()
    stop_l = {m.lower() for m in stop_markers}
    marker_idx = _find_line_idx(section, lambda ln: ln.lower() == marker_l, start)
    if marker_idx < 0:
        return []
    items: list[str] = []
    for line in section[marker_idx + 1 : marker_idx + 25]:
        lower = line.lower()
        if lower in stop_l or lower in {"education", "experience"}:
            break
        if _looks_like_tenure(line) or lower == "view details":
            continue
        if "fund" in lower and len(line) > 10:
            items.append(line)
    return items


# ---------------------------------------------------------------------------
# AMC inference from fund name
# ---------------------------------------------------------------------------


def _infer_amc(ctx: dict, report: ExtractionReport) -> None:
    if "amc" in ctx:
        return
    name = (ctx.get("fund_name") or "").lower()
    for hint, amc_name in _AMC_HINTS:
        if hint in name:
            ctx["amc"] = amc_name
            report.record("amc", "inferred_from_name")
            return


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deep_get(obj: Any, keys: list[str]) -> Any:
    cur = obj
    for k in keys:
        if isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return None
    return cur


def _coerce_str(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _coerce_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, re.Match):
        try:
            return float(val.group(1))
        except (ValueError, IndexError):
            return None
    try:
        return float(str(val).replace(",", "").strip())
    except ValueError:
        return None


def _parse_pct(text: str) -> float | None:
    m = re.search(r"(\d+\.?\d*)\s*%", text)
    return _coerce_float(m.group(1)) if m else None


def _parse_amount(text: str) -> float | None:
    m = re.search(r"(\d[\d,]*)", text)
    return _coerce_float(m.group(1).replace(",", "")) if m else None


def _try_set(
    ctx: dict,
    report: ExtractionReport,
    key: str,
    value: Any,
    tier: str,
) -> None:
    """Set ctx[key] only if not already set and value is non-None/non-empty."""
    if key in ctx:
        return
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    ctx[key] = value
    report.record(key, tier)
