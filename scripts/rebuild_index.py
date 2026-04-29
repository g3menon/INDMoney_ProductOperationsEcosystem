"""
Phase 4: Rebuild the RAG chunk index from the MF/fee corpus.

Reads source documents (fixture or scraped), chunks them, optionally generates
Gemini embeddings, and writes the result to backend/app/rag/index/chunks.json.

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
import json
import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _ensure_imports() -> None:
    backend = _repo_root() / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))


_FIXTURE_PATH = _repo_root() / "backend" / "app" / "rag" / "fixtures" / "mf_corpus.json"
_INDEX_PATH = _repo_root() / "backend" / "app" / "rag" / "index" / "chunks.json"

_MF_URLS = [
    "https://groww.in/mutual-funds/motilal-oswal-most-focused-midcap-30-fund-direct-growth",
    "https://groww.in/mutual-funds/motilal-oswal-most-focused-multicap-35-fund-direct-growth",
    "https://groww.in/mutual-funds/motilal-oswal-nifty-midcap-150-index-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-large-and-mid-cap-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
]

_TITLES = {
    "motilal-oswal-most-focused-midcap-30-fund-direct-growth": "Motilal Oswal Midcap Fund Direct Growth",
    "motilal-oswal-most-focused-multicap-35-fund-direct-growth": "Motilal Oswal Flexi Cap Fund Direct Growth",
    "motilal-oswal-nifty-midcap-150-index-fund-direct-growth": "Motilal Oswal Nifty Midcap 150 Index Fund Direct Growth",
    "hdfc-large-and-mid-cap-fund-direct-growth": "HDFC Large and Mid Cap Fund Direct Growth",
    "hdfc-equity-fund-direct-growth": "HDFC Flexi Cap Direct Plan Growth",
    "hdfc-large-cap-fund-direct-growth": "HDFC Large Cap Fund Direct Growth",
}


async def _scrape_document(url: str, today: str) -> "SourceDocument | None":
    from app.rag.ingest import clean_html_content, normalize_document_content
    from app.schemas.rag import SourceDocument

    slug = url.rstrip("/").split("/")[-1]
    title = _TITLES.get(slug, slug.replace("-", " ").title())
    doc_id = slug[:40]

    try:
        import httpx  # type: ignore

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            print(f"  WARN: {url} → HTTP {resp.status_code}")
            return None
        cleaned = clean_html_content(resp.text)
        normalized = normalize_document_content(cleaned)
        if len(normalized) < 200:
            print(f"  WARN: {url} → too little content ({len(normalized)} chars); using fixture")
            return None
        print(f"  OK: {url} → {len(normalized)} chars")
        return SourceDocument(
            doc_id=doc_id,
            url=url,
            title=title,
            doc_type="mutual_fund_page",
            last_checked=today,
            content=normalized,
        )
    except Exception as exc:
        print(f"  ERROR: {url} → {exc}")
        return None


def _load_fixture() -> list["SourceDocument"]:
    from app.schemas.rag import SourceDocument

    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return [SourceDocument.model_validate(r) for r in raw]


async def _build_index(
    use_fixture: bool,
    scrape: bool,
    embed: bool,
) -> None:
    from datetime import date

    today = date.today().isoformat()

    docs: list["SourceDocument"] = []

    if use_fixture:
        print(f"Loading fixture: {_FIXTURE_PATH}")
        docs = _load_fixture()
        print(f"  Loaded {len(docs)} fixture documents.")

    if scrape:
        print(f"Scraping {len(_MF_URLS)} MF/fee pages...")
        scraped = await asyncio.gather(*[_scrape_document(url, today) for url in _MF_URLS])
        scraped_docs = [d for d in scraped if d is not None]
        print(f"  Scraped {len(scraped_docs)} / {len(_MF_URLS)} pages.")
        # Scraped docs take precedence over fixture docs for the same URL.
        existing_urls = {d.url for d in scraped_docs}
        fixture_only = [d for d in docs if d.url not in existing_urls]
        docs = scraped_docs + fixture_only

    if not docs:
        print("ERROR: No documents to index. Use --use-fixture or --scrape.")
        sys.exit(1)

    print(f"\nChunking {len(docs)} documents...")
    from app.rag.chunk import chunk_document

    all_chunks: list["DocumentChunk"] = []
    for doc in docs:
        chunks = chunk_document(doc)
        print(f"  {doc.title[:50]}: {len(chunks)} chunks")
        all_chunks.extend(chunks)
    print(f"Total chunks: {len(all_chunks)}")

    if embed:
        print("\nGenerating Gemini embeddings (this may take a while)...")
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

    print(f"\nWriting index -> {_INDEX_PATH}")
    _INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = [c.model_dump() for c in all_chunks]
    _INDEX_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Done. {len(all_chunks)} chunks saved to {_INDEX_PATH}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild the Phase 4 RAG chunk index.")
    ap.add_argument("--use-fixture", action="store_true", help="Load fixture MF corpus (no network).")
    ap.add_argument("--scrape", action="store_true", help="Scrape live MF/fee pages from Groww.")
    ap.add_argument("--embed", action="store_true", help="Generate Gemini embeddings for each chunk.")
    args = ap.parse_args()

    if not args.use_fixture and not args.scrape:
        print("Specify at least --use-fixture or --scrape. Using --use-fixture as default.")
        args.use_fixture = True

    _ensure_imports()

    # Minimal env for Settings validation.
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
