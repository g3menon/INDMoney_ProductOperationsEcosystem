Phase 3 eval artifacts — Customer text chat foundation

Automated (available in this repo)
- Run: `cd backend; python -m app.evals.run_all --phase 3`
- Saves: `Deliverables/Evals/phase-3/eval_<timestamp>_phase3-v1.json` and `latest.json`

What the automated harness checks
- OpenAPI includes required chat endpoints (`/api/v1/chat/message`, `/api/v1/chat/prompts`, `/api/v1/chat/history/{session_id}`)
- Prompt chips response shape is valid (each chip has `id`, `label`, and `prompt`)
- A text chat roundtrip persists and `/history/{session_id}` returns the assistant message with the same `session_id`

Manual acceptance gate (text-only, before voice / Phase 8)
- Run `Docs/Runbook.md` End-to-end test → Step 3 (Customer text chat).
- Confirm MF + fee + hybrid prompts are answered grounded with citations, and session/history behave as expected (no voice required).
- Exercise at least one failure path from `Docs/Failures&EdgeCases.md` (Phase 3 section): empty tab on first load, prompt-chip validation parity, and/or refresh/session history behavior.

