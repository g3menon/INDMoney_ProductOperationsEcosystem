"""HTTP-only web scraper for non-Play-Store sources.

This module is for mutual fund and fee document pages. Playwright is reserved
for Play Store review collection only.
"""

from __future__ import annotations

import asyncio
import logging
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass
from typing import Mapping

import httpx

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
    "Gecko/20100101 Firefox/123.0"
)
BACKOFF_SECONDS = (1.0, 2.0, 4.0)


@dataclass(frozen=True)
class WebScraperError(Exception):
    """Structured fetch failure for HTTP document scraping."""

    url: str
    message: str
    status_code: int | None = None
    final_url: str | None = None

    def __str__(self) -> str:
        status = f" status={self.status_code}" if self.status_code is not None else ""
        final = f" final_url={self.final_url}" if self.final_url else ""
        return f"{self.message} url={self.url}{status}{final}"

    def to_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "message": self.message,
            "status_code": self.status_code,
            "final_url": self.final_url,
        }


@dataclass(frozen=True)
class WebPageFetchResult:
    url: str
    final_url: str
    status_code: int
    content: str
    content_type: str | None = None


async def fetch_web_page(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout_seconds: float = 25.0,
) -> WebPageFetchResult:
    """Fetch an HTML or JSON web page using httpx.AsyncClient.

    Retries failed requests with exponential backoff. robots.txt is checked for
    observability and logged, but it does not block the fetch.
    """
    merged_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        merged_headers.update(dict(headers))
    if not merged_headers.get("User-Agent"):
        merged_headers["User-Agent"] = DEFAULT_USER_AGENT

    await _log_robots_status(url, merged_headers["User-Agent"], timeout_seconds)

    last_error: WebScraperError | None = None
    async with httpx.AsyncClient(
        timeout=timeout_seconds,
        follow_redirects=True,
        headers=merged_headers,
    ) as client:
        for attempt in range(1, 4):
            try:
                resp = await client.get(url)
                content_type = resp.headers.get("content-type")
                if resp.status_code >= 400:
                    last_error = WebScraperError(
                        url=url,
                        message=f"HTTP {resp.status_code}",
                        status_code=resp.status_code,
                        final_url=str(resp.url),
                    )
                    logger.warning(
                        "web_fetch_http_error",
                        extra={
                            "url": url,
                            "status_code": resp.status_code,
                            "final_url": str(resp.url),
                            "attempt": attempt,
                        },
                    )
                else:
                    return WebPageFetchResult(
                        url=url,
                        final_url=str(resp.url),
                        status_code=resp.status_code,
                        content=resp.text,
                        content_type=content_type,
                    )
            except httpx.TimeoutException as exc:
                last_error = WebScraperError(url=url, message=f"timeout: {exc}")
                logger.warning(
                    "web_fetch_timeout",
                    extra={"url": url, "status_code": None, "error": str(exc), "attempt": attempt},
                )
            except httpx.HTTPError as exc:
                last_error = WebScraperError(url=url, message=str(exc))
                logger.warning(
                    "web_fetch_error",
                    extra={"url": url, "status_code": None, "error": str(exc), "attempt": attempt},
                )

            if attempt < 3:
                await asyncio.sleep(BACKOFF_SECONDS[attempt - 1])

    raise last_error or WebScraperError(url=url, message="unknown fetch failure")


async def _log_robots_status(url: str, user_agent: str, timeout_seconds: float) -> None:
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return
    robots_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))

    def _read_robots() -> bool | None:
        try:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(robots_url)
            parser.read()
            return parser.can_fetch(user_agent, url)
        except Exception:
            return None

    try:
        allowed = await asyncio.wait_for(asyncio.to_thread(_read_robots), timeout=min(timeout_seconds, 5.0))
    except Exception:
        allowed = None

    logger.info(
        "web_fetch_robots_checked",
        extra={"url": url, "robots_url": robots_url, "allowed": allowed},
    )
