Phase 4 eval artifacts — RAG and grounded hybrid Q&A

Automated
- Not available in `backend/app/evals/run_all.py` yet (current automated harness supports phases 1–3).

Manual acceptance gate (text-only, before voice / Phase 8)
- Run `Docs/Runbook.md` End-to-end test → Step 3 (Customer text chat).
- Validate groundedness and safety using `Docs/Rules.md` Phase 4 expectations:
  - Weak retrieval leads to bounded fallback (ask clarifying question or safe redirect), not fabricated answers.
  - MF-only, fee-only, and hybrid queries are supported in one coherent grounded response.
  - Citations/source attribution are present and correspond to the retrieved context.

Check also `Docs/Failures&EdgeCases.md` (Phase 4 section) for targeted failure scenarios:
- no retrieval hit
- low-quality retrieval hit
- ambiguous questions (e.g. “charges?”, “this fee?”)
- HTML/noise leakage (if you’re running through real ingestion + chunk/index rebuild)

Record
- Add screenshots/notes/log excerpts in this folder for:
  - at least one happy-path hybrid query
  - at least one “weak retrieval” fallback case

