"""HTTP-only mutual-fund NAV lookup from AMFI.

Uses AMFI's public latest NAV report (plain text). Optional Groww Playwright
enrichment during index rebuild is separate (see ``app.rag.mf_extractor``).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from time import monotonic

import httpx

logger = logging.getLogger(__name__)

AMFI_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
_CACHE_TTL_SECONDS = 6 * 60 * 60
_cache_text: str | None = None
_cache_loaded_at: float = 0.0

_TOKENIZE = re.compile(r"[a-z0-9]+")
_STOP_TOKENS = frozenset(
    [
        "fund",
        "scheme",
        "plan",
        "option",
        "regular",
        "direct",
        "growth",
        "gr",
        "idcw",
        "dividend",
        "payout",
        "reinvestment",
        "reinvest",
        "the",
        "and",
        "of",
    ]
)


@dataclass(frozen=True)
class MFNavLookupResult:
    scheme_code: str
    scheme_name: str
    nav: float
    nav_date: str
    source_url: str = AMFI_NAV_URL


async def lookup_latest_nav(fund_name: str) -> MFNavLookupResult | None:
    """Find the latest NAV for a fund name from AMFI's NAVAll.txt report."""
    if not fund_name.strip():
        return None
    try:
        text = await _fetch_amfi_nav_text()
    except Exception as exc:
        logger.warning(
            "mf_nav_lookup_fetch_failed",
            extra={"fund_name": fund_name[:80], "error": str(exc)[:160]},
        )
        return None
    result = find_latest_nav_in_amfi_text(fund_name=fund_name, nav_text=text)
    logger.info(
        "mf_nav_lookup_done",
        extra={
            "fund_name": fund_name[:80],
            "matched": bool(result),
            "scheme_code": result.scheme_code if result else None,
            "nav_date": result.nav_date if result else None,
        },
    )
    return result


async def _fetch_amfi_nav_text() -> str:
    global _cache_loaded_at, _cache_text
    now = monotonic()
    if _cache_text and now - _cache_loaded_at < _CACHE_TTL_SECONDS:
        return _cache_text

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"
        ),
        "Accept": "text/plain,*/*",
    }
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
        resp = await client.get(AMFI_NAV_URL)
        resp.raise_for_status()
        _cache_text = resp.text
        _cache_loaded_at = now
        return _cache_text


def find_latest_nav_in_amfi_text(
    fund_name: str,
    nav_text: str,
) -> MFNavLookupResult | None:
    """Parse AMFI NAVAll.txt and return the best matching scheme row."""
    target_tokens = _distinctive_tokens(fund_name)
    if len(target_tokens) < 2:
        return None

    requires_direct = "direct" in _tokens(fund_name)
    requires_growth = "growth" in _tokens(fund_name)
    best: tuple[float, MFNavLookupResult] | None = None

    for raw_line in nav_text.splitlines():
        line = raw_line.strip()
        if not line or ";" not in line or line.lower().startswith("scheme code"):
            continue
        parts = [part.strip() for part in line.split(";")]
        if len(parts) < 6:
            continue

        scheme_code, scheme_name, nav_raw, date_raw = parts[0], parts[3], parts[4], parts[5]
        scheme_tokens = _tokens(scheme_name)
        if requires_direct and "direct" not in scheme_tokens:
            continue
        if requires_growth and not ({"growth", "gr"} & scheme_tokens):
            continue
        if requires_direct and "regular" in scheme_tokens:
            continue

        nav = _parse_nav(nav_raw)
        nav_date = _parse_amfi_date(date_raw)
        if nav is None or nav_date is None:
            continue

        candidate_tokens = _distinctive_tokens(scheme_name)
        overlap = target_tokens & candidate_tokens
        if not overlap:
            continue

        query_coverage = len(overlap) / len(target_tokens)
        candidate_precision = len(overlap) / max(len(candidate_tokens), 1)
        score = (query_coverage * 0.75) + (candidate_precision * 0.25)
        if query_coverage < 0.68 or len(overlap) < 2:
            continue

        result = MFNavLookupResult(
            scheme_code=scheme_code,
            scheme_name=scheme_name,
            nav=nav,
            nav_date=nav_date,
        )
        if best is None or score > best[0]:
            best = (score, result)

    return best[1] if best else None


def _tokens(text: str) -> set[str]:
    normalized = (
        text.lower()
        .replace("mid-cap", "midcap")
        .replace("flexi-cap", "flexicap")
        .replace("large-cap", "largecap")
        .replace("small-cap", "smallcap")
    )
    raw = set(_TOKENIZE.findall(normalized))
    expanded = set(raw)
    for token, parts in {
        "midcap": ("mid", "cap"),
        "flexicap": ("flexi", "cap"),
        "largecap": ("large", "cap"),
        "smallcap": ("small", "cap"),
    }.items():
        if token in raw:
            expanded.update(parts)
    return expanded


def _distinctive_tokens(text: str) -> set[str]:
    tokens = _tokens(text)
    return {token for token in tokens if token not in _STOP_TOKENS}


def _parse_nav(value: str) -> float | None:
    try:
        nav = float(value.replace(",", "").strip())
    except ValueError:
        return None
    return nav if nav > 0 else None


def _parse_amfi_date(value: str) -> str | None:
    raw = value.strip()
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, fmt).date()
            # Guard against obviously stale parser mistakes while allowing old
            # fixtures in tests and delayed non-business-day NAV updates.
            if parsed > date.today() + timedelta(days=1):
                return None
            return parsed.isoformat()
        except ValueError:
            continue
    return None
