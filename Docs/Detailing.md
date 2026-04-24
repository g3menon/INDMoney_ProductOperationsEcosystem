# Architecture & implementation notes

## Hybrid RAG (single repo, single dashboard)

Use a **single-repo, single-dashboard, hybrid RAG** stack:

**BM25 + embeddings → RRF fusion → reranker → citation-constrained generation.**

This is the highest-probability setup for getting above **85%** on your evals.

### Four layers

1. **Ingestion / indexing**
2. **Hybrid retrieval**
3. **Reranking**
4. **Constrained answer generation**

---

## End-to-end flow

### 1. Document prep

- Collect official AMC / SEBI / AMFI + fee explainer docs.
- **Chunk by semantic section**, not fixed size only; preserve metadata such as:
  - `scheme_name`, `doc_type`, `topic`, `source_url`, `last_checked`

### 2. Dual indexes

- Build a **BM25** index from chunk text.
- Build a **vector** index from chunk embeddings.

### 3. Query pipeline

- Classify query type: **fact-only**, **fee-only**, **hybrid fact + fee**, or **disallowed** (advice / PII).
- If disallowed, **refuse immediately**.
- Otherwise retrieve top-*k* from BM25 and top-*k* from vector search **in parallel**.

### 4. Fusion + rerank

- Merge candidates with **RRF**.
- Rerank top **10–15** merged chunks with a **cross-encoder**.
- Keep only the top **3–5** chunks.

### 5. Answer generation

- Prompt the LLM to answer **only** from provided chunks.
- Force output shape: **exactly 6 bullets** for Pillar A hybrid answers, **source citations**, **last checked**, and **refusal** for advice / PII. A strict template improves citation reliability because the model is constrained to explicit source fields rather than free-form answering.

### Layer summary

| Layer | Recommendation | Why |
| --- | --- | --- |
| Chunking | Section-based chunks; **300–600 words** max | Fast to build; preserves finance context |
| Sparse retrieval | **BM25** | Strong for exact finance terminology |
| Dense retrieval | Gemini / Vertex embeddings or a local sentence-transformer | Good semantic recall |
| Fusion | **RRF** | Simple, effective baseline |
| Reranking | Optional but **strongly recommended** for the top ~10 candidates | Large eval win with limited added complexity |
| Generator | Claude in Cursor for dev; runtime can be Gemini / OpenAI / Claude per your stack | Keeps dev and production concerns separate |

---

## Hybrid system: internal vs external

| Audience | Use |
| --- | --- |
| **Internal** | Dashboard, weekly pulse, MCP actions, approvals |
| **External** | Voice agent interacting with users |

### Booking flow

1. The voice agent collects details from the user.
2. The system creates a **calendar hold**, **notes**, and **email draft** (via MCP).
3. A human advisor eventually takes the meeting.

You do **not** need to assume the product team is manually booking. The system handles it, with **human-in-the-loop** approval where required (e.g. approve / reject).

### Product guidance

1. Prefer **one advisor-facing** email; a second for **user confirmation** is optional but nice.
2. Stick with **Milestone 3** fixed topics (KYC, SIP, Statements, etc.). The Weekly Pulse adds context; it does not replace those topics.
3. Keep the greeting **neutral** and broadly helpful. Add a **light, optional** nudge—not a hard assumption.

---

## Important implementation notes

1. **STT and TTS** can be added **at the end**, after core logic is stable.
2. Introduce **MCP only in the HITL / approval layer**, not in the core latency-sensitive runtime. Direct integrations (e.g. Google STT, TTS, Calendar) stay the main execution path; MCP should play a **small, high-value** role where approval, traceability, and structured handoff matter more than raw speed. MCP fits standardized tool integration, permissions, and human-in-the-loop workflows—not every user-facing turn.

### Best place for MCP

The cleanest fit is **Pillar C: Human-in-the-Loop Approval Center**. The problem statement already expects approval-gated Notes/Doc and Email Draft actions after generation or a voice call, so MCP slots in without slowing chat or voice.

| Path | Use |
| --- | --- |
| **Direct APIs** | STT/TTS; live slot-finding; booking code generation; deployment interactions |
| **MCP** | Approval-gated email draft; structured note/doc append after approval; optional tentative calendar hold **only** after explicit approval if you want one more governed action |

Reserve approval for actions with **meaningful consequences** (emails, durable data changes), not every small interaction.
