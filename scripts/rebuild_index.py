"""
Phase 4: Rebuild the RAG chunk index and MF metrics index from the MF/fee corpus.

URLs are read from scripts/sources_manifest.json (single source of truth — no
hardcoded URL lists in this file).

Reads source documents (fixture or scraped), runs structured extraction, chunks
them, optionally generates Gemini embeddings, and writes:
  - backend/app/rag/index/chunks.json    (searchable RAG chunk index)
  - backend/app/rag/index/mf_metrics.json (structured metrics index for direct lookup)

Usage:
  # Use fixture data (no network required):
  python scripts/rebuild_index.py --use-fixture

  # Scrape live MF/fee pages then build (requires network):
  python scripts/rebuild_index.py --scrape

  # Scrape + generate Gemini embeddings (requires GEMINI_API_KEY):
  python scripts/rebuild_index.py --scrape --embed

  # Embed fixture data (requires GEMINI_API_KEY):
  python scripts/rebuild_index.py --use-fixture --embed
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
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


_MANIFEST_PATH = _repo_root() / "scripts" / "sources_manifest.json"
_FIXTURE_CORPUS_PATH = _repo_root() / "backend" / "app" / "rag" / "fixtures" / "mf_corpus.json"
_FIXTURE_METRICS_PATH = _repo_root() / "backend" / "app" / "rag" / "fixtures" / "mf_metrics.json"
_INDEX_DIR = _repo_root() / "backend" / "app" / "rag" / "index"
_CHUNKS_PATH = _INDEX_DIR / "chunks.json"
_METRICS_PATH = _INDEX_DIR / "mf_metrics.json"


def _load_manifest() -> list[dict]:
    if not _MANIFEST_PATH.exists():
        raise SystemExit(f"sources_manifest.json not found at {_MANIFEST_PATH}")
    raw = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    print(f"Manifest loaded: {len(raw)} source(s)")
    return raw


def _load_fixture_corpus() -> list["SourceDocument"]:
    from app.schemas.rag import SourceDocument

    raw = json.loads(_FIXTURE_CORPUS_PATH.read_text(encoding="utf-8"))
    return [SourceDocument.model_validate(r) for r in raw]


def _load_fixture_metrics() -> list[dict]:
    return json.loads(_FIXTURE_METRICS_PATH.read_text(encoding="utf-8"))


async def _scrape_document(
    entry: dict,
    today: str,
    scraped_at: str,
) -> "tuple[SourceDocument | None, dict | None]":
    from app.rag.ingest import clean_html_content, normalize_document_content
    from app.rag.mf_extractor import extract_from_html
    from app.schemas.rag import SourceDocument
    from app.integrations.web_scraper import fetch_web_page

    url: str = entry["url"]
    doc_id: str = entry["doc_id"]
    title: str = entry["title"]
    doc_type: str = entry.get("doc_type", "mutual_fund_page")

    try:
        fetched = await fetch_web_page(url)
        html = fetched.content
        cleaned = clean_html_content(html)
        normalized = normalize_document_content(cleaned)

        if len(normalized) < 200:
            print(
                f"  WARN  {doc_id}: {len(normalized)} chars after cleaning "
                "(JS-rendered content not accessible); falling back to fixture if available"
            )
            return None, None

        # Structured extraction.
        metrics, report = extract_from_html(
            html=html,
            url=url,
            doc_id=doc_id,
            normalized_text=normalized,
        )
        if metrics.nav is None:
            from app.integrations.mf_nav_provider import lookup_latest_nav

            nav_result = await lookup_latest_nav(metrics.fund_name)
            if nav_result is not None:
                metrics = metrics.model_copy(
                    update={
                        "nav": nav_result.nav,
                        "nav_date": nav_result.nav_date,
                        "nav_source_url": nav_result.source_url,
                    }
                )
                report.record("nav", "amfi_http")
                report.record("nav_date", "amfi_http")
        print(
            f"  OK    {doc_id}: {len(normalized):,} chars | "
            f"{len(report.fields_extracted)} fields extracted | "
            f"{len(report.js_only_missing)} snapshot fields missing"
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
        return doc, metrics.model_dump()

    except Exception as exc:
        print(f"  ERROR {doc_id}: {exc}")
        return None, None


async def _build_index(
    use_fixture: bool,
    scrape: bool,
    embed: bool,
) -> None:
    from datetime import date, datetime, timezone

    today = date.today().isoformat()
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest = _load_manifest()

    docs: list["SourceDocument"] = []
    metrics_records: list[dict] = []

    # ── Fixture pass ────────────────────────────────────────────────────────
    if use_fixture:
        print(f"\n[fixture] Loading corpus from {_FIXTURE_CORPUS_PATH}")
        fixture_docs = _load_fixture_corpus()
        print(f"  Loaded {len(fixture_docs)} fixture documents.")

        print(f"[fixture] Loading metrics from {_FIXTURE_METRICS_PATH}")
        fixture_metrics = _load_fixture_metrics()
        print(f"  Loaded {len(fixture_metrics)} fixture metric records.")

        docs.extend(fixture_docs)
        metrics_records.extend(fixture_metrics)

    # ── Scrape pass (takes precedence over fixture for the same doc_id) ────
    if scrape:
        print(f"\n[scrape] Fetching {len(manifest)} page(s)...")
        scraped_pairs = await asyncio.gather(
            *[_scrape_document(entry, today, scraped_at) for entry in manifest]
        )

        scraped_doc_ids: set[str] = set()
        for sdoc, smetrics in scraped_pairs:
            if sdoc is not None and smetrics is not None:
                scraped_doc_ids.add(sdoc.doc_id)
                # Replace fixture doc/metrics if scraped version is available.
                docs = [d for d in docs if d.doc_id != sdoc.doc_id]
                metrics_records = [m for m in metrics_records if m.get("doc_id") != sdoc.doc_id]
                docs.append(sdoc)
                metrics_records.append(smetrics)

        print(
            f"\n  Scraped {len(scraped_doc_ids)} / {len(manifest)} pages successfully."
        )
        if len(scraped_doc_ids) < len(manifest):
            missing = [e["doc_id"] for e in manifest if e["doc_id"] not in scraped_doc_ids]
            print(f"  Fixture fallback used for: {missing}")

    if not docs:
        print("ERROR: No documents to index. Use --use-fixture or --scrape.")
        sys.exit(1)

    # ── Chunk documents ──────────────────────────────────────────────────────
    print(f"\n[chunk] Chunking {len(docs)} document(s)...")
    from app.rag.chunk import chunk_document

    all_chunks: list[Any] = []
    for doc in docs:
        chunks = chunk_document(doc)
        print(f"  {doc.doc_id}: {len(chunks)} chunk(s)")
        all_chunks.extend(chunks)
    print(f"  Total chunks: {len(all_chunks)}")

    # ── Add structured metrics chunk per fund ────────────────────────────────
    # This makes structured MF metrics vector-searchable when --embed is enabled.
    from app.schemas.rag import DocumentChunk, MFFundMetrics

    metrics_by_doc_id: dict[str, dict] = {
        m.get("doc_id"): m for m in metrics_records if isinstance(m, dict) and m.get("doc_id")
    }

    metrics_chunks_added = 0
    for doc in docs:
        m_dict = metrics_by_doc_id.get(doc.doc_id)
        if not m_dict:
            continue
        try:
            metrics = MFFundMetrics.model_validate(m_dict)
        except Exception:
            continue

        content = _format_metrics_for_embedding(metrics)
        chunk_id = _stable_metrics_chunk_id(doc.doc_id)
        all_chunks.append(
            DocumentChunk(
                chunk_id=chunk_id,
                doc_id=doc.doc_id,
                source_url=doc.url,
                title=f"{doc.title} — Structured Metrics",
                doc_type=doc.doc_type,
                last_checked=doc.last_checked,
                content=content,
                chunk_index=9999,
            )
        )
        metrics_chunks_added += 1

    if metrics_chunks_added:
        print(f"\n[chunk] Added {metrics_chunks_added} structured metrics chunk(s).")

    # ── Optional embedding ──────────────────────────────────────────────────
    if embed:
        print("\n[embed] Generating Gemini embeddings...")
        from app.core.config import get_settings
        from app.rag.embeddings import EmbeddingIndex

        settings = get_settings()
        if not settings.gemini_api_key:
            print("  WARN: GEMINI_API_KEY not set; skipping embeddings.")
        else:
            emb_index = EmbeddingIndex()
            all_chunks = await emb_index.embed_chunks(all_chunks, settings)
            embedded = sum(1 for c in all_chunks if c.embedding is not None)
            print(f"  Embedded {embedded} / {len(all_chunks)} chunks.")

    # ── Write chunk index ───────────────────────────────────────────────────
    _INDEX_DIR.mkdir(parents=True, exist_ok=True)
    payload = [c.model_dump() for c in all_chunks]
    _CHUNKS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[write] chunks.json -> {_CHUNKS_PATH} ({len(all_chunks)} chunk(s))")

    # ── Write metrics index ─────────────────────────────────────────────────
    _METRICS_PATH.write_text(
        json.dumps(metrics_records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[write] mf_metrics.json -> {_METRICS_PATH} ({len(metrics_records)} record(s))")

    # ── Optional Supabase upsert ────────────────────────────────────────────
    enable_supabase = os.getenv("ENABLE_SUPABASE_WRITE", "").lower() in ("1", "true", "yes")
    if not enable_supabase:
        print("[supabase] Skipped (set ENABLE_SUPABASE_WRITE=true to persist to Supabase).")
    else:
        print("[supabase] ENABLE_SUPABASE_WRITE=true — upserting to Supabase...")
        from app.core.config import get_settings
        from app.repositories.mf_repository import get_mf_repository
        from app.schemas.rag import MFFundMetrics, SourceDocument

        try:
            sb_settings = get_settings()
            repo = get_mf_repository(sb_settings)

            async def _upsert_all() -> None:
                for doc in docs:
                    await repo.upsert_source_document(doc)
                for m_dict in metrics_records:
                    try:
                        metrics_obj = MFFundMetrics.model_validate(m_dict)
                        await repo.upsert_fund_metrics(metrics_obj)
                    except Exception as exc:
                        print(f"  WARN  {m_dict.get('doc_id', '?')}: metrics upsert failed — {exc}")

            asyncio.run(_upsert_all())
            print(f"[supabase] Upserted {len(docs)} source document(s) and {len(metrics_records)} metric record(s).")
        except Exception as exc:
            print(f"[supabase] WARN: Supabase write failed ({exc}); local index files are intact.")

    print("\nDone. Restart the backend server to load the updated indexes.")


def _stable_metrics_chunk_id(doc_id: str) -> str:
    """Deterministic chunk ID for the structured metrics chunk."""
    h = hashlib.sha256(f"{doc_id}:METRICS".encode("utf-8")).hexdigest()[:12].upper()
    return f"CHK-{h}"


def _jsonish(v: object) -> str:
    """Compact stable stringification for embedding payloads."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return v.strip() or "null"
    try:
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except Exception:
        return str(v)


def _format_metrics_for_embedding(metrics: "MFFundMetrics") -> str:
    """Include ALL requested fields as explicit keys for embedding."""
    r = metrics.returns.model_dump() if metrics.returns else None
    investment_returns = [row.model_dump() for row in metrics.investment_returns]
    returns_and_rankings = metrics.returns_and_rankings.model_dump() if metrics.returns_and_rankings else None
    top_holdings = [h.model_dump() for h in metrics.top_holdings]
    fund_managers = [m.model_dump() for m in metrics.fund_managers]
    sector_alloc = [s.model_dump() for s in metrics.sector_allocation]
    asset_alloc = metrics.asset_allocation or {}

    lines = [
        "STRUCTURED_MUTUAL_FUND_METRICS",
        f"fund_name: {_jsonish(metrics.fund_name)}",
        f"amc: {_jsonish(metrics.amc)}",
        f"category: {_jsonish(metrics.category)}",
        f"sub_category: {_jsonish(metrics.sub_category)}",
        f"plan: {_jsonish(metrics.plan)}",
        f"option: {_jsonish(metrics.option)}",
        f"nav: {_jsonish(metrics.nav)}",
        f"nav_date: {_jsonish(metrics.nav_date)}",
        f"nav_source_url: {_jsonish(metrics.nav_source_url)}",
        f"aum_cr: {_jsonish(metrics.aum_cr)}",
        f"expense_ratio_pct: {_jsonish(metrics.expense_ratio_pct)}",
        f"exit_load_pct: {_jsonish(metrics.exit_load_pct)}",
        f"exit_load_window_days: {_jsonish(metrics.exit_load_window_days)}",
        f"exit_load_description: {_jsonish(metrics.exit_load_description)}",
        f"risk_level: {_jsonish(metrics.risk_level)}",
        f"rating: {_jsonish(metrics.rating)}",
        f"benchmark: {_jsonish(metrics.benchmark)}",
        f"min_sip_amount: {_jsonish(metrics.min_sip_amount)}",
        f"min_lumpsum_amount: {_jsonish(metrics.min_lumpsum_amount)}",
        f"returns: {_jsonish(r)}",
        f"investment_returns: {_jsonish(investment_returns)}",
        f"returns_and_rankings: {_jsonish(returns_and_rankings)}",
        f"top_holdings: {_jsonish(top_holdings)}",
        f"advanced_ratios: {_jsonish(metrics.advanced_ratios)}",
        f"fund_managers: {_jsonish(fund_managers)}",
        f"sector_allocation: {_jsonish(sector_alloc)}",
        f"asset_allocation: {_jsonish(asset_alloc)}",
        f"fund_objective: {_jsonish(metrics.fund_objective)}",
        f"source_url: {_jsonish(metrics.source_url)}",
        f"scraped_at: {_jsonish(metrics.scraped_at)}",
        f"last_checked: {_jsonish(metrics.last_checked)}",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild the Phase 4 RAG chunk + metrics indexes.")
    ap.add_argument("--use-fixture", action="store_true", help="Load fixture MF corpus (no network).")
    ap.add_argument("--scrape", action="store_true", help="Scrape live MF/fee pages from Groww.")
    ap.add_argument("--embed", action="store_true", help="Generate Gemini embeddings for each chunk.")
    args = ap.parse_args()

    if not args.use_fixture and not args.scrape:
        print("No source specified. Defaulting to --use-fixture.")
        args.use_fixture = True

    _ensure_imports()

    os.environ.setdefault("APP_ENV", "build")
    os.environ.setdefault("FRONTEND_BASE_URL", "http://localhost:3000")
    os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "build-placeholder")

    from app.core.config import clear_settings_cache

    clear_settings_cache()
    asyncio.run(_build_index(use_fixture=args.use_fixture, scrape=args.scrape, embed=args.embed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
