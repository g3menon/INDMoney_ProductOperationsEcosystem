# Canonical sources — Groww Product Operations Ecosystem

Use this file as the **single list of URLs and collection rules** referenced from `Docs/Architecture.md`, `Docs/Runbook.md`, and `Docs/UI.md`. Do not auto-construct Groww fund URLs from display names; slugs drift after rebranding.

## Groww — Google Play Store (Playwright)

- **Listing (reviews):** https://play.google.com/store/apps/details?id=com.nextbillion.groww&hl=en_IN  
- **Collection:** **Playwright**, server-side or batch jobs only.  
- **Privacy:** Do **not** collect reviewer display names. **Do** collect **device type** (`Phone`, `Chromebook`, or `Tablet`) when shown on the listing.

### Example normalized review record (shape)

```json
{
  "review_id": "",
  "rating": 1,
  "text": "Example review text for schema validation only.",
  "date": "2026-02-14",
  "found_review_helpful": 21,
  "device": "Phone"
}
```

## Mutual fund pages to scrape (Groww public fund URLs)

**Motilal Oswal AMC**

| Scheme | URL |
| --- | --- |
| Motilal Oswal Midcap Fund Direct Growth | https://groww.in/mutual-funds/motilal-oswal-most-focused-midcap-30-fund-direct-growth |
| Motilal Oswal Flexi Cap Fund Direct Growth | https://groww.in/mutual-funds/motilal-oswal-most-focused-multicap-35-fund-direct-growth |
| Motilal Oswal Nifty Midcap 150 Index Fund Direct Growth | https://groww.in/mutual-funds/motilal-oswal-nifty-midcap-150-index-fund-direct-growth |

**HDFC AMC**

| Scheme | URL |
| --- | --- |
| HDFC Large and Mid Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-large-and-mid-cap-fund-direct-growth |
| HDFC Flexi Cap Direct Plan Growth | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| HDFC Large Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |

**Scraping note:** Groww may keep **legacy URL slugs** after scheme renames (e.g. Flexi Cap path still uses `hdfc-equity-fund-direct-growth`). Always use the URLs in this table—do not derive slugs from current scheme titles alone.

## Fee explainer corpus (same fund pages)

Expense ratio and exit load (and related fee copy) appear **on each fund page** linked above. Use those pages as the **fee explainer** source material for RAG—not a separate Product-tab “fee tutorial” surface.

**Design intent for analytics:** active funds in this set carry higher expense ratios (~0.5–1%) vs the Motilal Nifty Midcap 150 index fund (~0.15–0.30%), surfacing an active vs passive fee contrast in the dataset.

## Reference UI (visual inspiration only)

- Product / pulse + email layout inspiration: https://dribbble.com/shots/26857590-CallAI-AI-Voice-Assistants-Dashboard-Design  
- Customer chat: https://dribbble.com/shots/26057790-Ultima-AI-Dashboard-Your-Smart-Chat-Partner and https://dribbble.com/shots/26756293-Voice-AI-Automation-Dashboard  
- Advisor: https://dribbble.com/shots/25680703-Voice-AI-Agent-Configurations  
