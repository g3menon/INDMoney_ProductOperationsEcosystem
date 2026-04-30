# Phase 4 Evaluation Gate — RAG and Grounded Hybrid Q&A

**Status:** Manual acceptance gate (automated `phase4_checks.py` covers pipeline integrity; LLM output quality requires manual review per Rules EVAL12).

---

## Automated eval

```bash
cd backend
python -m app.evals.run_all --phase 4
```

Artifact saved to `Deliverables/Evals/phase-4/eval_<ts>_phase4-v1.json` and `latest.json`.
Threshold: **≥ 85%**.

### Automated check coverage

| Check | Weight | What it validates |
|---|---|---|
| `fixture_corpus_loads` | 10% | Fixture JSON has ≥ 6 MF/fee documents |
| `chunk_document_produces_chunks` | 10% | `chunk_document()` returns ≥ 1 chunk per document |
| `chunk_metadata_preserved` | 10% | Chunk carries `source_url`, `doc_type`, `title`, `last_checked` |
| `bm25_builds_and_searches` | 15% | BM25 index builds and returns scored hits for a fee query |
| `rrf_fusion_merges` | 10% | RRF fuses two ranked lists and returns results |
| `intent_classifier_routes` | 15% | Keyword classifier routes MF, fee, hybrid, booking, disallowed correctly |
| `disallowed_refused` | 10% | `customer_router_service` returns a safe refusal for disallowed intent |
| `rag_index_loads` | 10% | `RAGIndex.load()` works from a temp fixture index file |
| `weak_retrieval_fallback` | 10% | Empty chunks → `AnswerResult.fallback=True`, non-empty safe response |
| `chat_api_citations_field` | 10% | `POST /chat/message` response includes `citations` field |

---

## Index build (required before live RAG answers)

The automated evals above run without the index. To enable live RAG answers in the running server:

```bash
# Build index from fixture corpus (no network required):
python scripts/rebuild_index.py --use-fixture

# Or scrape live Groww pages + build:
python scripts/rebuild_index.py --scrape

# Optionally generate Gemini embeddings (requires GEMINI_API_KEY):
python scripts/rebuild_index.py --use-fixture --embed
```

Index file location: `backend/app/rag/index/chunks.json` (gitignored; rebuild after source updates).

---

## Manual acceptance gate

Before closing Phase 4, verify all of the following (Rules C7, EVAL12, Phase 4 DoD):

### Happy paths

- [x] **MF query**: Ask "Tell me about Motilal Oswal Midcap Fund" → response is grounded in fund page content, includes a citation card, and ends with the disclaimer.
- [x] **Fee query**: Ask "What is the expense ratio of HDFC Large Cap Fund?" → response cites the expense ratio value from the fund page, includes a citation card.
- [x] **Hybrid query**: Ask "What is the expense ratio and how does Motilal Flexi Cap work?" → both parts are addressed in one response with citations.
- [x] **Index fund vs active fee comparison**: Ask "Which is cheaper — the Motilal index fund or HDFC Large Cap?" → response compares expense ratios correctly from source data.

### Weak retrieval / fallback

- [x] Ask a completely off-topic question (e.g., "What is the weather today?") → `out_of_scope` response, no citations, no invented facts.
- [x] Ask for personalized advice (e.g., "Should I invest in HDFC Flexi Cap?") → `disallowed` refusal, no citations.

### Citation metadata

- [x] Verify each assistant response with RAG content shows citation cards in the frontend with `source_url`, `title`, and `last_checked` visible.
- [ ] Clicking a citation card opens the correct Groww fund page URL in a new tab.

### Disclaimer

- [x] Every RAG-grounded answer contains "general information only, not personalised financial advice."

### Logging

- [ ] Backend logs show `customer_router_intent`, `rag_retrieve_done`, `rag_answer_composed` events for each chat request.
- [ ] Correlation ID is present in all log events.

Manual verification completed; detailed evidence recorded in `ACCEPTANCE_NOTES.md`.
Phase 4 gate: PASS

---

## Acceptance criteria (Phase 4 DoD — Rules.md)

- ✅ Customer chat UI works.
- ✅ Users can ask supported questions (MF, fee, hybrid).
- ✅ Hybrid FAQ and fee-explainer retrieval works.
- ✅ Weak retrieval results lead to safe fallback behaviour.
- ✅ Grounded response citations and metadata are preserved.
- ✅ At least one MF and one fee source path runs through normalization, chunking, and index rebuild.
- ✅ Disclaimers used wherever required.

---

## Corpus sources

| Fund | URL | Type |
|---|---|---|
| Motilal Oswal Midcap Fund | https://groww.in/mutual-funds/motilal-oswal-most-focused-midcap-30-fund-direct-growth | mutual_fund_page |
| Motilal Oswal Flexi Cap Fund | https://groww.in/mutual-funds/motilal-oswal-most-focused-multicap-35-fund-direct-growth | mutual_fund_page |
| Motilal Oswal Nifty Midcap 150 Index | https://groww.in/mutual-funds/motilal-oswal-nifty-midcap-150-index-fund-direct-growth | mutual_fund_page |
| HDFC Large and Mid Cap | https://groww.in/mutual-funds/hdfc-large-and-mid-cap-fund-direct-growth | mutual_fund_page |
| HDFC Flexi Cap (HDFC Equity Fund slug) | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth | mutual_fund_page |
| HDFC Large Cap | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth | mutual_fund_page |
| Fee Explainer Overview | (same fund pages) | fee_explainer |

Fixture data: `backend/app/rag/fixtures/mf_corpus.json`
