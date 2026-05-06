"""Incremental source fetching from scripts/sources_manifest.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.integrations.web_scraper import WebPageFetchResult, WebScraperError, fetch_web_page

DEFAULT_SCRAPE_INTERVAL_HOURS = 24


@dataclass(frozen=True)
class SourceEntry:
    doc_id: str
    url: str
    title: str
    doc_type: str
    scrape_interval_hours: int = DEFAULT_SCRAPE_INTERVAL_HOURS


@dataclass(frozen=True)
class SourceFetchOutcome:
    entry: SourceEntry
    fetched: bool
    result: WebPageFetchResult | None = None
    skipped_reason: str | None = None
    error: WebScraperError | None = None


class SourceFetcher:
    """Fetch manifest sources incrementally and persist per-URL fetch state."""

    def __init__(
        self,
        manifest_path: Path | None = None,
        state_path: Path | None = None,
        default_interval_hours: int = DEFAULT_SCRAPE_INTERVAL_HOURS,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        self.manifest_path = manifest_path or repo_root / "scripts" / "sources_manifest.json"
        self.state_path = state_path or repo_root / "scripts" / "source_fetch_state.json"
        self.default_interval_hours = default_interval_hours
        self._state: dict[str, dict[str, Any]] = self._load_state()

    def load_manifest(self) -> list[SourceEntry]:
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"sources manifest not found: {self.manifest_path}")
        raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("sources_manifest.json must contain a list of source entries.")

        entries: list[SourceEntry] = []
        for idx, row in enumerate(raw):
            if not isinstance(row, dict):
                raise ValueError(f"manifest entry {idx} must be an object.")
            entries.append(
                SourceEntry(
                    doc_id=str(row["doc_id"]),
                    url=str(row["url"]),
                    title=str(row["title"]),
                    doc_type=str(row.get("doc_type", "mutual_fund_page")),
                    scrape_interval_hours=int(
                        row.get("scrape_interval_hours") or self.default_interval_hours
                    ),
                )
            )
        return entries

    def should_fetch(self, entry: SourceEntry, *, force: bool = False) -> bool:
        if force:
            return True
        state = self._state.get(entry.url) or {}
        last_fetched = _parse_datetime(state.get("last_fetched"))
        if last_fetched is None:
            return True
        age_hours = (datetime.now(timezone.utc) - last_fetched).total_seconds() / 3600
        return age_hours >= entry.scrape_interval_hours

    async def fetch_sources(self, *, force: bool = False) -> list[SourceFetchOutcome]:
        outcomes: list[SourceFetchOutcome] = []
        for entry in self.load_manifest():
            if not self.should_fetch(entry, force=force):
                outcomes.append(
                    SourceFetchOutcome(
                        entry=entry,
                        fetched=False,
                        skipped_reason=f"fetched within {entry.scrape_interval_hours}h interval",
                    )
                )
                continue

            try:
                result = await fetch_web_page(entry.url)
                self._record_success(entry, result)
                outcomes.append(SourceFetchOutcome(entry=entry, fetched=True, result=result))
            except WebScraperError as exc:
                self._record_failure(entry, exc)
                outcomes.append(SourceFetchOutcome(entry=entry, fetched=False, error=exc))

            self._write_state()
        return outcomes

    def _load_state(self) -> dict[str, dict[str, Any]]:
        if not self.state_path.exists():
            return {}
        raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}

    def _write_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _record_success(self, entry: SourceEntry, result: WebPageFetchResult) -> None:
        self._state[entry.url] = {
            "doc_id": entry.doc_id,
            "last_fetched": datetime.now(timezone.utc).isoformat(),
            "status_code": result.status_code,
            "final_url": result.final_url,
            "error": None,
        }

    def _record_failure(self, entry: SourceEntry, error: WebScraperError) -> None:
        self._state[entry.url] = {
            "doc_id": entry.doc_id,
            "last_attempted": datetime.now(timezone.utc).isoformat(),
            "status_code": error.status_code,
            "final_url": error.final_url,
            "error": error.message,
        }


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None
