"""
Phase 2 + Phase 4 ingestion.

Phase 2 (--mode reviews): raw Play Store JSON -> cleaned + normalized -> persist to Supabase.
  Pipeline (authoritative): raw persist -> cleaning -> normalization -> (optional segment) -> theme -> pulse.

Phase 4 (--mode mf_sources): scrape MF/fee pages -> clean HTML -> structured extract
  -> normalize text -> chunk -> persist (local JSON + optional Supabase).
  URLs are read from scripts/sources_manifest.json (single source of truth).
  For index building, run scripts/rebuild_index.py after this step.

Usage:
  # Phase 2 (default):
  python scripts/ingest_sources.py --in reviews_raw.json

  # Phase 4: validate fixture MF corpus and report chunks:
  python scripts/ingest_sources.py --mode mf_sources --use-fixture

  # Phase 4: scrape live MF/fee pages:
  python scripts/ingest_sources.py --mode mf_sources

  # Phase 4: skip Supabase writes (local JSON only):
  INGEST_SKIP_SUPABASE=1 python scripts/ingest_sources.py --mode mf_sources
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _ensure_imports() -> None:
    backend = _repo_root() / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))


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

_FIXTURE_CORPUS_PATH = _repo_root() / "backend" / "app" / "rag" / "fixtures" / "mf_corpus.json"
_FIXTURE_METRICS_PATH = _repo_root() / "backend" / "app" / "rag" / "fixtures" / "mf_metrics.json"
_MANIFEST_PATH = _repo_root() / "scripts" / "sources_manifest.json"
_INDEX_DIR = _repo_root() / "backend" / "app" / "rag" / "index"


def _load_manifest() -> list[dict]:
    if not _MANIFEST_PATH.exists():
        raise SystemExit(f"sources_manifest.json not found at {_MANIFEST_PATH}")
    raw = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    print(f"Manifest loaded: {len(raw)} source(s) from {_MANIFEST_PATH}")
    return raw


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

    from datetime import date, datetime, timezone

    today = date.today().isoformat()
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest = _load_manifest()

    docs: list[SourceDocument] = []
    metrics_list: list[Any] = []

    # ── Fixture mode ────────────────────────────────────────────────────────
    if use_fixture:
        print(f"\n[fixture] Loading corpus from {_FIXTURE_CORPUS_PATH}")
        raw_corpus = json.loads(_FIXTURE_CORPUS_PATH.read_text(encoding="utf-8"))
        docs = [SourceDocument.model_validate(r) for r in raw_corpus]
        print(f"  Loaded {len(docs)} fixture documents.")

        print(f"[fixture] Loading metrics from {_FIXTURE_METRICS_PATH}")
        metrics_list = json.loads(_FIXTURE_METRICS_PATH.read_text(encoding="utf-8"))
        print(f"  Loaded {len(metrics_list)} fixture metric records.")

    # ── Live scrape mode ────────────────────────────────────────────────────
    else:
        """
        Mutual fund and fee pages are fetched using httpx.AsyncClient only.
        Playwright is not used here. Playwright is exclusively used for
        Play Store review collection in scripts/fetch_groww_playstore_reviews.py.
        """

        from app.integrations.web_scraper import WebScraperError, fetch_web_page
        from app.rag.mf_extractor import extract_from_html

        print(f"\n[scrape] Fetching {len(manifest)} page(s)...")

        async def _scrape_all() -> tuple[list[SourceDocument], list[Any]]:
            scraped_docs: list[SourceDocument] = []
            scraped_metrics: list[Any] = []

            for entry in manifest:
                url: str = entry["url"]
                doc_id: str = entry["doc_id"]
                title: str = entry["title"]
                doc_type: str = entry.get("doc_type", "mutual_fund_page")

                try:
                    fetched = await fetch_web_page(url)
                    html = fetched.content
                    print(
                        f"  FETCH {doc_id}: {len(html):,} bytes fetched "
                        f"(HTTP {fetched.status_code}, final_url={fetched.final_url})"
                    )

                    cleaned = clean_html_content(html)
                    normalized = normalize_document_content(cleaned)

                    if len(normalized) < 200:
                        print(
                            f"  WARN  {doc_id}: only {len(normalized)} chars after cleaning"
                            " - content may be JS-rendered; try --use-fixture"
                        )

                    # Structured extraction.
                    metrics, report = extract_from_html(
                        html=html,
                        url=url,
                        doc_id=doc_id,
                        normalized_text=normalized,
                    )
                    extracted_count = len(report.fields_extracted)
                    missing_count = len(report.fields_missing)
                    print(
                        f"  EXTR  {doc_id}: {extracted_count} fields extracted, "
                        f"{missing_count} missing "
                        f"(tiers: {sorted(set(report.tier_used.values()))})"
                    )
                    if report.js_only_missing:
                        print(
                            f"  INFO  {doc_id}: JS-only fields not available: "
                            f"{report.js_only_missing}"
                        )

                    doc = SourceDocument(
                        doc_id=doc_id,
                        url=url,
                        title=title,
                        doc_type=doc_type,  # type: ignore[arg-type]
                        last_checked=today,
                        content=normalized,
                        scraped_at=scraped_at,
                    )
                    scraped_docs.append(doc)
                    scraped_metrics.append(metrics.model_dump())
                    print(f"  OK    {doc_id}: doc + metrics ready")

                except WebScraperError as exc:
                    print(f"  ERROR {doc_id}: {exc}")
                except Exception as exc:
                    print(f"  ERROR {doc_id}: {exc}")

            return scraped_docs, scraped_metrics

        docs, metrics_list = asyncio.run(_scrape_all())

        if not docs:
            print(
                "\nNo pages scraped successfully. "
                "Consider --use-fixture or check network connectivity.\n"
                "Groww pages are Next.js / React apps; some fields may not be available from raw HTML."
            )
            return 1

    # ── Chunk documents ──────────────────────────────────────────────────────
    print(f"\n[chunk] Chunking {len(docs)} document(s)...")
    total_chunks = 0
    for doc in docs:
        chunks = chunk_document(doc)
        print(f"  {doc.doc_id}: {len(chunks)} chunk(s)")
        total_chunks += len(chunks)
    print(f"  Total chunks: {total_chunks}")

    # ── Persist metrics locally ──────────────────────────────────────────────
    _INDEX_DIR.mkdir(parents=True, exist_ok=True)
    metrics_path = _INDEX_DIR / "mf_metrics.json"
    metrics_path.write_text(
        json.dumps(metrics_list, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[persist] mf_metrics.json -> {metrics_path} ({len(metrics_list)} record(s))")

    # ── Optional Supabase persistence ────────────────────────────────────────
    enable_supabase = os.getenv("ENABLE_SUPABASE_WRITE", "").lower() in ("1", "true", "yes")
    if not enable_supabase:
        print("[persist] Supabase writes skipped (set ENABLE_SUPABASE_WRITE=true to enable).")
    else:
        from app.core.config import get_settings
        from app.repositories.mf_repository import get_mf_repository
        from app.schemas.rag import MFFundMetrics

        try:
            settings = get_settings()
            repo = get_mf_repository(settings)

            async def _persist_to_supabase() -> None:
                for doc, m_dict in zip(docs, metrics_list):
                    await repo.upsert_source_document(doc)
                    try:
                        metrics_obj = MFFundMetrics.model_validate(m_dict)
                        await repo.upsert_fund_metrics(metrics_obj)
                    except Exception as exc:
                        print(f"  WARN  {doc.doc_id}: metrics validation failed — {exc}")

            asyncio.run(_persist_to_supabase())
            print(f"[persist] Supabase upserts complete for {len(docs)} document(s).")
        except Exception as exc:
            print(f"[persist] WARN: Supabase persistence failed ({exc}); local files are intact.")

    print(
        "\nNext steps:\n"
        "  python scripts/rebuild_index.py --use-fixture   # rebuild searchable chunk index\n"
        "  python scripts/rebuild_index.py --scrape        # scrape + rebuild index\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

