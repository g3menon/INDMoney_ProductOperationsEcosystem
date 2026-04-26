"""
Play Store review collection job (Phase 2, Playwright).

Rules:
- Server/batch only (never frontend).
- No reviewer names.
- Persist raw records first, then run cleaning/normalization before any LLM step.

Usage (local):
  python scripts/fetch_groww_playstore_reviews.py --limit 50 --out reviews_raw.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

from playwright.sync_api import sync_playwright


GROWW_PLAYSTORE_URL = "https://play.google.com/store/apps/details?id=com.nextbillion.groww&hl=en_IN"


def collect_reviews(limit: int = 50) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(GROWW_PLAYSTORE_URL, wait_until="domcontentloaded", timeout=60_000)

        # Scroll to load reviews section
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(1500)

        # Best-effort selectors: Play Store DOM changes frequently.
        # We keep this minimal and rely on logs/repair when it breaks (I10).
        review_cards = page.locator("div.RHo1pe").all()
        for card in review_cards:
            if len(rows) >= limit:
                break

            # Note: Do not capture profile names.
            text = (card.locator("div.h3YV2d").first.text_content() or "").strip()
            rating_label = card.locator("div.iXRFPc").first.get_attribute("aria-label") or ""
            rating = 0
            for token in rating_label.split():
                if token.isdigit():
                    rating = int(token)
                    break
            date_txt = (card.locator("span.bp9Aid").first.text_content() or "").strip()

            # Device type is sometimes shown; default Unknown.
            device = "Unknown"
            meta = card.locator("div.RpB6p").first.text_content() or ""
            for d in ("Phone", "Chromebook", "Tablet"):
                if d.lower() in meta.lower():
                    device = d
                    break

            rows.append(
                {
                    "source": "playstore",
                    "review_id": f"dom-{len(rows)+1}",
                    "rating": rating if rating else 3,
                    "text": text,
                    "review_date": None,  # parsing Play Store date formats is deferred
                    "found_review_helpful": None,
                    "device": device,
                    "collected_at": datetime.utcnow().isoformat(),
                }
            )

        browser.close()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--out", type=str, default="reviews_raw.json")
    args = ap.parse_args()

    rows = collect_reviews(limit=args.limit)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(rows)} raw reviews to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

