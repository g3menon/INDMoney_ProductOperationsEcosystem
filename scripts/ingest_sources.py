"""
Phase 2 ingestion: raw Play Store JSON -> cleaned + normalized -> persist to Supabase.

Pipeline (authoritative): raw persist -> cleaning -> normalization -> (optional segment) -> theme -> pulse.

Usage:
  python scripts/ingest_sources.py --in reviews_raw.json
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
    ap.add_argument("--in", dest="infile", required=True, help="Raw JSON file from Playwright collector.")
    args = ap.parse_args()

    _ensure_imports()

    from app.core.config import clear_settings_cache, get_settings
    from app.repositories.pulse_repository import get_pulse_repository
    from app.rag.ingest import normalize_raw_reviews
    from app.schemas.pulse import RawReview

    clear_settings_cache()
    settings = get_settings()
    repo = get_pulse_repository(settings)

    with open(args.infile, "r", encoding="utf-8") as f:
        payload: Any = json.load(f)
    if not isinstance(payload, list):
        raise SystemExit("Input JSON must be a list of raw review objects.")

    raw_rows: list[RawReview] = []
    for i, row in enumerate(payload):
        try:
            raw_rows.append(RawReview.model_validate(row))
        except Exception as exc:
            raise SystemExit(f"Row {i} failed schema validation: {exc}") from exc

    normalized, stats = normalize_raw_reviews(raw_rows)

    async def _persist() -> tuple[int, int]:
        rc = 0
        if os.getenv("INGEST_SKIP_RAW", "").lower() not in ("1", "true", "yes"):
            rc = await repo.persist_raw_reviews(raw_rows)
        nc = await repo.persist_normalized_reviews(normalized)
        return rc, nc

    rc, nc = asyncio.run(_persist())

    print(
        json.dumps(
            {
                "input_rows": stats.input_rows,
                "raw_persisted": rc,
                "normalized_kept": stats.kept,
                "normalized_persisted": nc,
                "dropped_short": stats.dropped_short,
                "dropped_non_english": stats.dropped_non_english,
                "dropped_dupe": stats.dropped_dupe,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

