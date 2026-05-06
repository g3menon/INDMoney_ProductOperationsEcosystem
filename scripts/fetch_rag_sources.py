"""Fetch manifest RAG sources and persist chunks to Supabase.

Mutual fund and fee pages are fetched with httpx via SourceFetcher/web_scraper.
If RAG_STORAGE_MODE=file, chunks.json is also written for local compatibility.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _ensure_imports() -> None:
    backend = _repo_root() / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))


_INDEX_DIR = _repo_root() / "backend" / "app" / "rag" / "index"
_CHUNKS_PATH = _INDEX_DIR / "chunks.json"


async def _run(embed: bool, force: bool) -> int:
    from app.core.config import clear_settings_cache, get_settings
    from app.integrations.source_fetcher import SourceFetcher
    from app.rag.chunk import chunk_document
    from app.rag.embeddings import EmbeddingIndex
    from app.rag.ingest import clean_html_content, normalize_document_content
    from app.rag.mf_extractor import extract_from_html
    from app.repositories.rag_repository import SupabaseRAGRepository
    from app.schemas.rag import SourceDocument

    clear_settings_cache()
    settings = get_settings()
    storage_mode = (settings.rag_storage_mode or "file").lower().strip()

    today = date.today().isoformat()
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    fetcher = SourceFetcher()
    outcomes = await fetcher.fetch_sources(force=force)
    fetched = [outcome for outcome in outcomes if outcome.fetched and outcome.result is not None]
    skipped = [outcome for outcome in outcomes if outcome.skipped_reason]
    failed = [outcome for outcome in outcomes if outcome.error is not None]

    print(f"[fetch] fetched={len(fetched)} skipped={len(skipped)} failed={len(failed)}")
    for outcome in skipped:
        print(f"  SKIP  {outcome.entry.doc_id}: {outcome.skipped_reason}")
    for outcome in failed:
        print(f"  ERROR {outcome.entry.doc_id}: {outcome.error}")

    docs: list[SourceDocument] = []
    metrics_records: list[dict[str, Any]] = []
    for outcome in fetched:
        entry = outcome.entry
        assert outcome.result is not None
        html = outcome.result.content
        cleaned = clean_html_content(html)
        normalized = normalize_document_content(cleaned)
        metrics, report = extract_from_html(
            html=html,
            url=entry.url,
            doc_id=entry.doc_id,
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
        docs.append(
            SourceDocument(
                doc_id=entry.doc_id,
                url=entry.url,
                title=entry.title,
                doc_type=entry.doc_type,  # type: ignore[arg-type]
                last_checked=today,
                content=normalized,
                scraped_at=scraped_at,
            )
        )
        metrics_records.append(metrics.model_dump())
        print(
            f"  OK    {entry.doc_id}: {len(normalized):,} chars | "
            f"{len(report.fields_extracted)} fields extracted"
        )

    if not docs:
        print("[chunk] No newly fetched documents to chunk.")
        return 0

    chunks = []
    for doc in docs:
        doc_chunks = chunk_document(doc)
        chunks.extend(doc_chunks)
        print(f"[chunk] {doc.doc_id}: {len(doc_chunks)} chunk(s)")
    print(f"[chunk] total={len(chunks)}")

    if embed:
        if not settings.gemini_api_key:
            print("[embed] GEMINI_API_KEY not set; skipping embeddings.")
        else:
            print("[embed] Generating Gemini embeddings...")
            emb_index = EmbeddingIndex()
            chunks = await emb_index.embed_chunks(chunks, settings)
            embedded = sum(1 for chunk in chunks if chunk.embedding is not None)
            print(f"[embed] embedded={embedded}/{len(chunks)}")

    repo = SupabaseRAGRepository(settings)
    await repo.upsert_chunks_batch(chunks)
    stats = await repo.get_stats()
    print(f"[supabase] upserted={len(chunks)} stats={stats}")

    if storage_mode == "file":
        _INDEX_DIR.mkdir(parents=True, exist_ok=True)
        existing = []
        if _CHUNKS_PATH.exists():
            existing_raw = json.loads(_CHUNKS_PATH.read_text(encoding="utf-8"))
            if isinstance(existing_raw, list):
                existing = existing_raw
        incoming = [chunk.model_dump() for chunk in chunks]
        incoming_ids = {row["chunk_id"] for row in incoming}
        merged = [row for row in existing if row.get("chunk_id") not in incoming_ids]
        merged.extend(incoming)
        _CHUNKS_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[file] chunks.json -> {_CHUNKS_PATH} ({len(merged)} chunk(s))")

    if metrics_records:
        metrics_path = _INDEX_DIR / "mf_metrics.json"
        _INDEX_DIR.mkdir(parents=True, exist_ok=True)
        existing_metrics = []
        if metrics_path.exists():
            raw_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            if isinstance(raw_metrics, list):
                existing_metrics = raw_metrics
        incoming_doc_ids = {row.get("doc_id") for row in metrics_records}
        merged_metrics = [row for row in existing_metrics if row.get("doc_id") not in incoming_doc_ids]
        merged_metrics.extend(metrics_records)
        metrics_path.write_text(json.dumps(merged_metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[file] latest mf_metrics.json -> {metrics_path} ({len(merged_metrics)} record(s))")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch RAG source pages and upsert rag_chunks in Supabase.")
    ap.add_argument("--embed", action="store_true", help="Generate Gemini embeddings before upsert.")
    ap.add_argument("--force", action="store_true", help="Ignore source_fetch_state.json freshness windows.")
    args = ap.parse_args()

    _ensure_imports()
    os.environ.setdefault("RAG_STORAGE_MODE", "file")
    return asyncio.run(_run(embed=args.embed, force=args.force))


if __name__ == "__main__":
    raise SystemExit(main())
