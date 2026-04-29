"""Phase 4: Structured mutual-fund metrics extractor for Groww MF pages.

Extraction strategy (four tiers, applied in order, results merged):
  Tier 1 — URL slug  : derives plan, option, initial fund_name (always works).
  Tier 2 — __NEXT_DATA__ JSON : Next.js SSR page props; may contain category,
            AMC, risk, benchmark, minimums, expense ratio.
  Tier 3 — BeautifulSoup HTML : structured selectors for visible page sections;
            supplements Tier 2 for fields not in SSR props.
  Tier 4 — Regex on normalized text : reliable fallback for fields present as
            narrative prose (expense ratio, exit load, category, risk, minimums).

Fields that require JavaScript rendering (Tier 3 — JS-only) are set to None
and reported ONCE via ExtractionReport.log_summary(), not scattered as warnings.

Interface contract for Playwright compatibility:
  Pass Playwright-rendered HTML as the `html` argument — no other code changes
  are needed.  The same four tiers run; Tiers 2-3 will find more data.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.schemas.rag import MFFundMetrics, MFHolding, MFReturns, MFSectorAlloc

logger = logging.getLogger(__name__)

# Fields that are almost certainly unavailable without JS rendering.
_JS_ONLY_FIELDS: frozenset[str] = frozenset(
    [
        "nav",
        "nav_date",
        "aum_cr",
        "rating",
        "returns",
        "top_holdings",
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
    js_only_missing: list[str] = field(default_factory=list)

    def record(self, fname: str, tier: str) -> None:
        if fname not in self.fields_extracted:
            self.fields_extracted.append(fname)
        self.tier_used[fname] = tier

    def missing(self, fname: str, js_only: bool = False) -> None:
        if fname not in self.fields_missing:
            self.fields_missing.append(fname)
        if js_only and fname not in self.js_only_missing:
            self.js_only_missing.append(fname)

    def log_summary(self) -> None:
        if self.js_only_missing:
            logger.warning(
                "mf_extractor_js_only_fields_missing",
                extra={
                    "doc_id": self.doc_id,
                    "fields_unavailable": self.js_only_missing,
                    "reason": (
                        "js_rendered_only — rerun with Playwright-rendered HTML "
                        "to populate these fields"
                    ),
                },
            )
        non_js_missing = [
            f for f in self.fields_missing if f not in self.js_only_missing
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
        html: Raw or Playwright-rendered page HTML.
        url: Canonical source URL.
        doc_id: Stable document identifier (e.g. slug[:40]).
        normalized_text: Pre-cleaned text from ``ingest.normalize_document_content``.
            Used as Tier 4 regex fallback.

    Returns:
        Tuple of (MFFundMetrics, ExtractionReport).  Fields unavailable from the
        current HTML tier are None; ExtractionReport.log_summary() emits one
        consolidated warning for JS-only fields.
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
        top_holdings=ctx.get("top_holdings") or [],
        sector_allocation=ctx.get("sector_allocation") or [],
        asset_allocation=ctx.get("asset_allocation") or {},
        fund_objective=ctx.get("fund_objective"),
        source_url=url,
        scraped_at=scraped_at,
        last_checked=scraped_at[:10],
    )

    # Mark JS-only fields as missing once.
    for fname in _JS_ONLY_FIELDS:
        val = getattr(metrics, fname, None)
        if not val:
            report.missing(fname, js_only=True)

    report.log_summary()
    return metrics, report


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
