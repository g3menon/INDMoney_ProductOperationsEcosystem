"""
Play Store review collection job (Phase 2, Playwright).

Rules:
- Server/batch only (never frontend).
- No reviewer names.
- Persist raw records first, then run cleaning/normalization before any LLM step.

Usage (local):
  python scripts/fetch_groww_playstore_reviews.py --limit 200 --out reviews_raw.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


GROWW_PLAYSTORE_URL = "https://play.google.com/store/apps/details?id=com.nextbillion.groww&hl=en_IN"


def _log(msg: str) -> None:
    print(f"[playstore] {msg}", flush=True)


def _stable_review_id(seed: str) -> str:
    return "rw-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _parse_rating(label: str) -> int:
    # Examples observed: "Rated 5 stars out of five stars"
    for token in (label or "").split():
        if token.isdigit():
            v = int(token)
            if 1 <= v <= 5:
                return v
    return 0


def _collect_from_card(card) -> dict[str, Any] | None:
    # Important: do not collect reviewer names.
    try:
        text = (card.locator("div.h3YV2d").first.text_content(timeout=800) or "").strip()
    except Exception:
        text = ""
    if not text:
        # fallback selectors for text
        try:
            text = (card.locator("[data-expandable-text]").first.text_content(timeout=800) or "").strip()
        except Exception:
            text = ""
    if not text:
        return None

    try:
        rating_label = card.locator("div.iXRFPc[aria-label]").first.get_attribute("aria-label", timeout=800) or ""
    except Exception:
        rating_label = ""
    if not rating_label:
        try:
            rating_label = (
                card.locator("[aria-label*='Rated'][aria-label*='star']").first.get_attribute("aria-label", timeout=800)
                or ""
            )
        except Exception:
            rating_label = ""
    rating = _parse_rating(rating_label) or 3

    # Device type is sometimes shown; default Unknown.
    device = "Unknown"
    try:
        meta = (card.locator("div.RpB6p").first.text_content(timeout=800) or "").strip()
    except Exception:
        meta = ""
    for d in ("Phone", "Chromebook", "Tablet"):
        if d.lower() in meta.lower():
            device = d
            break

    # We do not parse date formats here; store null and rely on ingestion to set if available.
    seed = f"{rating}|{device}|{text[:200]}"
    return {
        "source": "playstore",
        "review_id": _stable_review_id(seed),
        "rating": rating,
        "text": text,
        "review_date": None,
        "found_review_helpful": None,
        "device": device,
        "collected_at": datetime.utcnow().isoformat(),
    }


def _find_scroll_target(page, root):
    # Play Store reviews are usually inside a nested scrollable element (not always the dialog node itself).
    candidates = [
        "div[role='dialog'] .fysCi",
        "div[role='dialog'] .DWPxHb",
        "div[role='dialog'] .PfaPzd",
        "div[role='dialog']",
    ]
    for sel in candidates:
        loc = page.locator(sel).first
        try:
            if loc.count() > 0 and loc.is_visible():
                return loc
        except Exception:
            continue
    return root


def _scroll_and_wait(page, scroll_target) -> None:
    # Try several scroll gestures because Play Store review overlays drift often.
    try:
        scroll_target.evaluate(
            "(el) => { el.scrollTop = el.scrollHeight; el.dispatchEvent(new Event('scroll')); }"
        )
    except Exception:
        pass
    try:
        scroll_target.evaluate("(el) => { el.scrollBy(0, Math.max(1800, el.clientHeight * 2)); }")
    except Exception:
        pass
    try:
        page.mouse.wheel(0, 9000)
    except Exception:
        pass
    try:
        page.keyboard.press("End")
    except Exception:
        pass
    page.wait_for_timeout(1800)


def collect_reviews(limit: int = 50) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    no_progress_attempts = 0
    max_no_progress_attempts = 8
    iteration = 0

    _log(f"Requested limit={limit}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.set_default_timeout(5000)

        _log(f"Navigating to listing: {GROWW_PLAYSTORE_URL}")
        page.goto(GROWW_PLAYSTORE_URL, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(2500)

        # Try to open the "See all reviews" dialog if present (more reliable than inline section).
        see_all_selectors = [
            "text=/See all reviews/i",
            "a[href*='reviews']",
            "button:has-text('See all reviews')",
        ]
        opened_dialog = False
        for sel in see_all_selectors:
            loc = page.locator(sel).first
            try:
                if loc.count() > 0 and loc.is_visible():
                    _log(f"Clicking reviews entrypoint: {sel}")
                    loc.click(timeout=5000)
                    page.wait_for_timeout(1500)
                    opened_dialog = True
                    break
            except Exception:
                continue

        # Candidate card selectors (Play Store drifts; keep multiple).
        card_selectors = [
            "div.RHo1pe",  # common review card wrapper
            "div:has(div.h3YV2d)",  # fallback if wrapper drifts
        ]

        # If dialog opened, try to scope to it; otherwise, operate on page.
        root = page
        dialog = page.locator("div[role='dialog']").first
        try:
            if opened_dialog and dialog.count() > 0 and dialog.is_visible():
                root = dialog
        except Exception:
            root = page

        # Expand "More" buttons inside cards when present.
        def _expand_more() -> None:
            more_buttons = root.locator("button:has-text('More'), button:has-text('more')").all()
            for b in more_buttons[:50]:
                try:
                    if b.is_visible():
                        b.click(timeout=1500)
                except Exception:
                    continue

        scroll_target = _find_scroll_target(page, root)

        # Keep loading until limit reached or repeated no-progress indicates exhaustion.
        while len(rows) < limit and no_progress_attempts < max_no_progress_attempts:
            iteration += 1
            _expand_more()

            before_count = len(rows)

            # Apply several scroll strategies to trigger lazy loading reliably.
            _scroll_and_wait(page, scroll_target)
            _expand_more()
            page.wait_for_timeout(700)

            # Re-parse cards after every load attempt.
            candidates = []
            sel = card_selectors[0]
            try:
                candidates = root.locator(sel).all()
            except Exception:
                candidates = []
            if not candidates:
                sel = card_selectors[1]
                try:
                    candidates = root.locator(sel).all()
                except Exception:
                    candidates = []

            if not candidates:
                no_progress_attempts += 1
                _log(
                    f"iter={iteration}: no candidate cards, collected={len(rows)}, "
                    f"no_progress={no_progress_attempts}/{max_no_progress_attempts}"
                )
                continue

            _log(
                f"iter={iteration}: found {len(candidates)} cards via {sel}, "
                f"collected={len(rows)}, no_progress={no_progress_attempts}/{max_no_progress_attempts}"
            )
            for card in candidates[: min(len(candidates), limit * 6)]:
                if len(rows) >= limit:
                    break
                try:
                    row = _collect_from_card(card)
                except Exception:
                    row = None
                if not row:
                    continue
                # Dedupe by review_id
                rid = str(row.get("review_id", ""))
                if not rid:
                    continue
                if rid in seen_ids:
                    continue
                seen_ids.add(rid)
                rows.append(row)

            if len(rows) > before_count:
                no_progress_attempts = 0
                _log(f"iter={iteration}: progress {before_count} -> {len(rows)}")
            else:
                no_progress_attempts += 1
                _log(
                    f"iter={iteration}: no new rows, collected={len(rows)}, "
                    f"no_progress={no_progress_attempts}/{max_no_progress_attempts}"
                )

        browser.close()

    rows = rows[:limit]
    # Hard cap: never persist more than 200 reviews regardless of --limit.
    rows = rows[:200]
    logger.info("review_collection_complete", extra={"count": len(rows), "capped_at": 200})
    _log(f"Collected {len(rows)} reviews (requested={limit}).")
    if len(rows) < limit:
        _log(f"Only {len(rows)} reviews available/retrievable; target was {limit}.")
    if len(rows) == 0:
        raise RuntimeError(
            "Zero reviews collected. Play Store DOM selectors likely changed. "
            "Re-run with network access and update card selectors in scripts/fetch_groww_playstore_reviews.py."
        )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--out", type=str, default="reviews_raw.json")
    args = ap.parse_args()

    rows = collect_reviews(limit=args.limit)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(rows)} raw reviews to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

