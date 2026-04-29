"""
Phase 2 + Phase 4 ingestion.

Phase 2 (--mode reviews): raw Play Store JSON -> cleaned + normalized -> persist to Supabase.
  Pipeline (authoritative): raw persist -> cleaning -> normalization -> (optional segment) -> theme -> pulse.

Phase 4 (--mode mf_sources): scrape MF/fee pages -> clean HTML -> normalize -> chunk.
  For index building, run scripts/rebuild_index.py after this step.

Usage:
  # Phase 2 (default):
  python scripts/ingest_sources.py --in reviews_raw.json

  # Phase 4: validate fixture MF corpus and report chunks:
  python scripts/ingest_sources.py --mode mf_sources --use-fixture

  # Phase 4: scrape live MF/fee pages:
  python scripts/ingest_sources.py --mode mf_sources
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _ensure_imports() -> None:
    root = _repo_root()
    backend = os.path.join(root, "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--mode",
        choices=["reviews", "mf_sources"],
        default="reviews",
        help="Ingestion mode: 'reviews' (Phase 2) or 'mf_sources' (Phase 4).",
    )
    ap.add_argument(
        "--in",
        dest="infile",
        default=None,
        help="Raw JSON file from Playwright collector (--mode reviews only).",
    )
    ap.add_argument(
        "--use-fixture",
        action="store_true",
        help="Use fixture MF corpus instead of live scraping (--mode mf_sources only).",
    )
    args = ap.parse_args()

    if args.mode == "mf_sources":
        return _run_mf_sources(use_fixture=args.use_fixture)

    # Phase 2 reviews mode.
    if not args.infile:
        ap.error("--in is required for --mode reviews")
    return _run_reviews(args.infile)


# ---------------------------------------------------------------------------
# Phase 2: Play Store reviews ingestion
# ---------------------------------------------------------------------------


def _run_reviews(infile: str) -> int:
    _ensure_imports()

    from app.core.config import clear_settings_cache, get_settings
    from app.rag.ingest import normalize_raw_reviews
    from app.repositories.pulse_repository import get_pulse_repository
    from app.schemas.pulse import RawReview

    clear_settings_cache()
    settings = get_settings()
    repo = get_pulse_repository(settings)

    with open(infile, "r", encoding="utf-8") as f:
        payload: Any = json.load(f)
    if not isinstance(payload, list):
        raise SystemExit("Input JSON must be a list of raw review objects.")

    raw_rows: list[RawReview] = []
    for i, row in enumerate(payload):
        try:
            raw_rows.append(RawReview.model_validate(row))
        except Exception as exc:
            raise SystemExit(f"Row {i} failed schema validation: {exc}") from exc

    async def _persist() -> tuple[int, int]:
        rc = 0
        if os.getenv("INGEST_SKIP_RAW", "").lower() not in ("1", "true", "yes"):
            rc = await repo.persist_raw_reviews(raw_rows)
        normalized, stats = normalize_raw_reviews(raw_rows)
        nc = await repo.persist_normalized_reviews(normalized)
        skipped = int(stats.input_rows - stats.kept)
        print(f"Raw rows read: {stats.input_rows} | Normalized: {stats.kept} | Skipped: {skipped}")
        return rc, nc

    asyncio.run(_persist())
    return 0


# ---------------------------------------------------------------------------
# Phase 4: MF / fee sources ingestion
# ---------------------------------------------------------------------------

_MF_URLS = [
    "https://groww.in/mutual-funds/motilal-oswal-most-focused-midcap-30-fund-direct-growth",
    "https://groww.in/mutual-funds/motilal-oswal-most-focused-multicap-35-fund-direct-growth",
    "https://groww.in/mutual-funds/motilal-oswal-nifty-midcap-150-index-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-large-and-mid-cap-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
]

_FIXTURE_PATH = os.path.join(_repo_root(), "backend", "app", "rag", "fixtures", "mf_corpus.json")


def _run_mf_sources(use_fixture: bool = False) -> int:
    _ensure_imports()

    os.environ.setdefault("APP_ENV", "build")
    os.environ.setdefault("FRONTEND_BASE_URL", "http://localhost:3000")
    os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "build-placeholder")

    from app.core.config import clear_settings_cache
    from app.rag.chunk import chunk_document
    from app.rag.ingest import clean_html_content, normalize_document_content
    from app.schemas.rag import SourceDocument

    clear_settings_cache()

    from datetime import date

    today = date.today().isoformat()
    docs: list[SourceDocument] = []

    if use_fixture:
        print(f"Using fixture data from {_FIXTURE_PATH}")
        raw = json.loads(open(_FIXTURE_PATH, encoding="utf-8").read())
        docs = [SourceDocument.model_validate(r) for r in raw]
        print(f"Loaded {len(docs)} fixture documents.")
    else:
        print(f"Scraping {len(_MF_URLS)} MF/fee pages (this may take a moment)...")
        import httpx  # type: ignore

        async def _scrape_all() -> list[SourceDocument]:
            result: list[SourceDocument] = []
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                for url in _MF_URLS:
                    slug = url.rstrip("/").split("/")[-1]
                    doc_id = slug[:40]
                    try:
                        headers = {"User-Agent": "Mozilla/5.0 (compatible; GrowwOpsBot/1.0)"}
                        resp = await client.get(url, headers=headers)
                        if resp.status_code != 200:
                            print(f"  WARN: {url} → HTTP {resp.status_code}; skipping")
                            continue
                        cleaned = clean_html_content(resp.text)
                        normalized = normalize_document_content(cleaned)
                        if len(normalized) < 200:
                            print(f"  WARN: {url} → too little content; skipping")
                            continue
                        print(f"  OK: {url} → {len(normalized)} chars")
                        result.append(
                            SourceDocument(
                                doc_id=doc_id,
                                url=url,
                                title=slug.replace("-", " ").title(),
                                doc_type="mutual_fund_page",
                                last_checked=today,
                                content=normalized,
                            )
                        )
                    except Exception as exc:
                        print(f"  ERROR: {url} → {exc}")
            return result

        docs = asyncio.run(_scrape_all())
        if not docs:
            print("No pages scraped. Consider --use-fixture or check network connectivity.")
            return 1

    print(f"\nChunking {len(docs)} documents...")
    total_chunks = 0
    for doc in docs:
        chunks = chunk_document(doc)
        print(f"  {doc.title[:50]}: {len(chunks)} chunks")
        total_chunks += len(chunks)

    print(f"\nTotal chunks: {total_chunks}")
    print("Run 'python scripts/rebuild_index.py --use-fixture' to build the searchable index.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
