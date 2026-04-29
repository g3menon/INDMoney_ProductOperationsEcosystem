# Phase 4 Extended — Manual Acceptance Notes

**Scope:** Structured MF metrics scraping, direct metric lookup, hybrid answer composition.
**Status:** Manual acceptance gate (run automated evals first, then verify scenarios below).

---

## Pre-flight: rebuild the indexes

```bash
# Fixture-based (no network required):
python scripts/rebuild_index.py --use-fixture

# Live scrape (network required; some fields will be None due to JS rendering):
python scripts/rebuild_index.py --scrape

# With embeddings:
python scripts/rebuild_index.py --use-fixture --embed
```

Both `chunks.json` and `mf_metrics.json` are written to `backend/app/rag/index/`.
Restart the backend after rebuilding.

---

## Automated eval

```bash
cd backend
python -m app.evals.run_all --phase 4
```

Threshold: **≥ 85%**. Artifact saved to `Deliverables/Evals/phase-4/`.

---

## Manual acceptance scenarios

### A. Direct metric questions (structured lookup — no LLM)

These should return a deterministic answer with a single citation card.

| Query | Expected behaviour |
|---|---|
| `What is the expense ratio of HDFC Large Cap Fund?` | Returns `0.75% per annum` with ₹75/yr note; cites groww.in/hdfc-large-cap |
| `What is the expense ratio of Motilal Oswal Midcap Fund?` | Returns `0.58%`; cites motilal midcap URL |
| `What is the exit load for HDFC Flexi Cap?` | Returns `1% within 1 year`; cites hdfc-equity URL |
| `What is the minimum SIP for Motilal Nifty Midcap 150?` | Returns `₹500`; cites motilal index URL |
| `What is the exit load for the Motilal index fund?` | Returns `0.1% within 15 days` |

**Checklist:**
- [ ] Answer is deterministic (same response on repeated calls, no LLM variance).
- [ ] Citation card appears with correct `source_url`, `title`, `last_checked`.
- [ ] Disclaimer present in every response.
- [ ] No invented figures — fields not available say "not available (requires live page data)".

---

### B. Direct metric — fund not identifiable

| Query | Expected behaviour |
|---|---|
| `What is the expense ratio?` | Returns clarifying question asking which fund |
| `What is the NAV?` | Returns clarifying question |

**Checklist:**
- [ ] Clarifying response, no citation, no invented fund name.

---

### C. Hybrid query — metrics + RAG narrative (Gemini)

These should return an answer that leads with structured facts then uses RAG text for explanation.

| Query | Expected behaviour |
|---|---|
| `What is the expense ratio of HDFC Large Cap and how does it compare to an index fund?` | States 0.75% for HDFC Large Cap; references 0.20% for Motilal index fund from RAG context |
| `Explain the fees for Motilal Oswal Midcap Fund` | Leads with TER 0.58%, exit load 1%/15 days; explains what TER covers using RAG narrative |
| `Tell me about HDFC Large and Mid Cap Fund including its fees` | Combines fund overview (category, risk, minimums) with fee details |

**Checklist:**
- [ ] Structured metrics appear accurately (not hallucinated).
- [ ] RAG narrative supplements facts with explanation.
- [ ] Citations include both the metrics source and any retrieved chunks.
- [ ] Disclaimer present.

---

### D. General RAG queries (unchanged Phase 4 path)

| Query | Expected behaviour |
|---|---|
| `Tell me about Motilal Oswal Midcap Fund` | Grounded RAG answer from fund page; citation card |
| `What is an expense ratio?` | RAG/fee_query answer explaining TER concept |
| `Compare direct plan vs regular plan fees` | RAG answer from fee explainer document |

**Checklist:**
- [ ] Response grounded in corpus, not invented.
- [ ] Citation cards present with `source_url`, `title`, `last_checked`.
- [ ] Disclaimer present.

---

### E. Weak retrieval / fallback

| Query | Expected behaviour |
|---|---|
| `What is the weather today?` | `out_of_scope` response; no citations; no invented content |
| `Should I invest in HDFC Flexi Cap?` | `disallowed` refusal; no citations |
| `Predict whether Motilal Midcap will go up` | `disallowed` refusal |

**Checklist:**
- [ ] No fabricated answers.
- [ ] No citation cards for refusals.

---

### F. Field availability transparency

When fields are `None` (JS-rendered-only), the structured answer should say so explicitly.

- [ ] `What is the NAV of HDFC Large Cap?` → "NAV: not available (requires live page data)" with source URL.
- [ ] `What are the top holdings of Motilal Midcap?` → "Top Holdings: not available (requires live page data)".

---

### G. Source manifest and extractor logs

Run the scrape with verbose mode to verify per-field logs:

```bash
python scripts/ingest_sources.py --mode mf_sources
```

**Checklist:**
- [ ] Each fund shows `FETCH`, `EXTR`, `OK` log lines.
- [ ] `EXTR` shows fields extracted count and tiers used.
- [ ] JS-only fields listed in `INFO` line (not scattered as individual warnings).
- [ ] `mf_metrics.json` written to `backend/app/rag/index/`.

---

### H. Adding a new fund (manifest only — no code change)

1. Add one entry to `scripts/sources_manifest.json`:
   ```json
   {
     "doc_id": "parag-parikh-flexicap-direct",
     "url": "https://groww.in/mutual-funds/parag-parikh-long-term-equity-fund-direct-growth",
     "title": "Parag Parikh Flexi Cap Fund Direct Growth",
     "doc_type": "mutual_fund_page"
   }
   ```
2. Run `python scripts/rebuild_index.py --scrape`.
3. Restart backend.
4. Ask: "What is the expense ratio of Parag Parikh Flexi Cap?" → should route to `direct_metric_query`.

**Checklist:**
- [ ] No code changes required to add the fund.
- [ ] New fund appears in mf_metrics.json after rebuild.
- [ ] Direct metric questions about the new fund work after restart.

---

## Schema validation

- [ ] `infra/supabase/phase4_schema.sql` includes `mf_fund_metrics` table.
- [ ] `mf_fund_metrics` has FK to `source_documents(doc_id) ON DELETE CASCADE`.
- [ ] `INGEST_SKIP_SUPABASE=1` prevents Supabase writes; local JSON still written.

---

## Acceptance criteria (Phase 4 extended DoD)

- [ ] Direct metric questions return deterministic structured answers for all 6 fixture funds.
- [ ] Hybrid questions combine structured metrics + RAG narrative with Gemini.
- [ ] Fund not matched → clarifying question (no invented fund data).
- [ ] JS-only fields (`nav`, `aum_cr`, `returns`, `top_holdings`, `sector_allocation`) are None with inline note.
- [ ] Source manifest drives both scripts; no hardcoded URLs in script logic.
- [ ] `mf_metrics.json` written alongside `chunks.json` on every rebuild.
- [ ] `mf_fund_metrics` Supabase table DDL present and additive.
- [ ] `MFMetricsStore` loads at startup alongside `RAGIndex`; absent file degrades gracefully.
- [ ] All existing Phase 4 automated eval checks still pass at ≥ 85%.
- [ ] Disclaimer present in all structured, hybrid, and RAG answers.
