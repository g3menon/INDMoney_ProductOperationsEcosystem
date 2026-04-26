# Groww Product Operations Ecosystem — Rules & Guardrails

This document defines the implementation rules, constraints, and execution guardrails for the integrated Groww Product Operations Ecosystem. All contributors and AI coding agents must follow these rules for every phase.

The system combines:
- Customer support and fee explanation.
- Weekly pulse generation from review intelligence.
- Booking and advisor operations workflows.
- Google integrations.
- Dashboard surfaces for customer, product, and advisor roles.

## How to use this file

- Treat these rules as implementation constraints, not suggestions.
- If a generated solution conflicts with these rules, the rules win.
- If architecture changes materially, update this file together with architecture docs and `.env.example`.
- A phase is not complete until its Definition of Done is satisfied.

## Global rules

| ID | Rule | Why it exists |
|---|---|---|
| G1 | **Do not overengineer.** Prefer the simplest implementation that satisfies the current phase. Avoid speculative abstractions, unnecessary frameworks, and future-proofing that is not currently needed. | Build time and token budget are limited. |
| G2 | **Preserve architecture boundaries.** Frontend handles presentation, backend handles orchestration/domain logic, and external writes happen only through integration services. | Prevents logic sprawl and duplication. |
| G3 | **Text-first before voice; full E2E without STT/TTS.** Every customer and advisor workflow must work in **typed text and normal UI** before voice (Phase 8) is required for acceptance. **Phases 1–7** must be testable end-to-end per `Docs/Runbook.md` **End-to-end test (text-only, before voice)** without microphone or TTS. | Voice is an adapter; STT/TTS must not gate validation of core product behavior. |
| G4 | **Voice is adapter-only.** STT/TTS may transform input/output only; they must not contain business logic, workflow logic, or integration logic. | Ensures parity between text and voice flows. |
| G5 | **No secrets in code.** All credentials, keys, tokens, model IDs, sheet IDs, sender emails, and integration values must come from environment variables or approved config layers. | Security and deployability. |
| G6 | **No unnecessary PII in logs, prompts, exports, or analytics.** Only the minimum needed data may be stored or processed. | Reduces privacy risk. |
| G7 | **Fail gracefully.** Known failure modes must return safe user-facing fallbacks and actionable logs. The system must not crash silently. | External APIs and LLMs will fail intermittently. |
| G8 | **Structured logging is mandatory.** Logs must include correlation IDs, layer context, durations, and normalized error categories. | Enables debugging across multi-step workflows. |
| G9 | **Idempotency is required for side effects.** Retries must not create duplicate emails, calendar events, sheet writes, approval actions, or bookings. | Prevents duplicate real-world actions. |
| G10 | **Documentation must match implementation.** `README.md`, architecture docs, `Docs/Rules.md`, `Docs/UserFlow.md`, `Docs/UI.md`, `Deliverables/Resources.md`, and `.env.example` must stay aligned with the actual code. | Prevents documentation drift. |
| G11 | **Pin dependencies where practical.** Use deterministic versions for backend and frontend packages. | Improves reproducibility and debugging. |
| G12 | **Every phase must be manually testable.** A phase is not complete unless its core happy path can be exercised manually. | Ensures visible, working progress. |
| G13 | **Prefer one source of truth.** Shared states, constants, schemas, and workflow enums must live in central modules rather than repeated ad hoc. | Prevents inconsistency across layers. |
| G14 | **Only approved, cleaned context reaches LLMs.** Retrieval inputs, review data, booking context, and operational context must be bounded, relevant, and sanitized first. | Controls cost, safety, and hallucination risk. |
| G15 | **Token usage must be intentional.** Minimize prompt size, redundant retries, duplicate summarization, and repeated transformations. | Keeps development and runtime efficient. |
| G16 | **No hidden architecture drift.** New folders, services, or abstractions must align with the documented architecture before they are introduced. | Prevents AI-generated repo sprawl. |
| G17 | **No hardcoded fallback magic values in production paths.** Default behavior may exist, but fake IDs, fake URLs, fake times, or silent mock fallbacks must not leak into real logic. | Avoids hard-to-find production bugs. |
| G18 | **Groww Play Store ingestion uses Playwright in server or batch context only.** Do not ship Play Store automation in the Next.js client bundle; pin browser versions in CI; cap concurrency and retries to respect rate limits and provider stability. | Keeps secrets and automation off the public web surface and reduces ban risk. |
| G19 | **Collected text must pass cleaning then normalization before chunking, indexing, or pulse LLM steps.** Raw Play Store payloads and scraped HTML must be stripped of markup/boilerplate (**cleaning**), then deduped, schema-mapped, and policy-filtered (**normalization**) before chunks hit retrieval indexes or before **theme / pulse** generation runs. | Prevents garbage chunks, duplicate themes, and unstable RAG/pulse quality. |

## UI and UX rules

| ID | Rule | Enforcement |
|---|---|---|
| UI1 | **Every screen must support five UI states:** loading, empty, partial, error, and ideal. | No screen may assume perfect data availability. |
| UI2 | **No blank dashboards.** Empty states must explain why data is absent and what action the user can take next. | Use helper text and CTA where relevant. |
| UI3 | **Loading must be visible quickly.** If an action takes noticeable time, show a spinner, skeleton, or inline processing state immediately. | Prevents the UI from feeling frozen. |
| UI4 | **Error states must be actionable.** Every recoverable error should include retry guidance, fallback messaging, or a next step. | Never show raw stack traces in the UI. |
| UI5 | **Partial success must be explicit.** If one panel succeeds and another fails, show both results honestly rather than blocking the whole page. | Important for dashboard resilience. |
| UI6 | **Cross-tab consistency is mandatory.** Customer, Product, and Advisor tabs must share status language, badge conventions, spacing rhythm, and interaction patterns. | Prevents cognitive friction. |
| UI7 | **State-changing actions require visible feedback.** Approve, reject, book, cancel, send, retry, and refresh actions must show pending, success, and failure states. | No silent updates. |
| UI8 | **Do not rely on color alone.** Status and severity must include text labels or icons, not just color differences. | Accessibility and clarity. |
| UI9 | **Forms validate inline.** Required fields, malformed inputs, invalid dates, and unsupported actions must be caught before submission when possible. | Reduces avoidable failures. |
| UI10 | **Destructive actions need confirmation.** Reject, cancel, resend, or overwrite actions must require confirmation or a clear undo path. | Protects users from accidental mistakes. |
| UI11 | **Responsive usability is required from day one.** The app must remain usable on common laptop and tablet widths even if phone optimization is limited initially. | Prevents layout breakage. |
| UI12 | **Keyboard-friendly operation is required for core workflows.** Navigation, chat submission, approval actions, and tab changes must work without a mouse. | Accessibility and operator speed. |
| UI13 | **Timezone context must always be visible** for booking slots, confirmations, and operational timestamps. | Prevents scheduling errors. |
| UI14 | **Do not show fake success.** If a process is still underway, show `processing`, `queued`, or `pending`, not `done`. | Preserves user trust. |
| UI15 | **Use reusable shared state components.** `LoadingState`, `EmptyState`, `ErrorState`, `InlineStatus`, and `ConfirmationBanner` should be shared components. | Keeps the interface consistent. |
| UI16 | **Use optimistic updates only when rollback is defined.** If UI state changes before backend confirmation, rollback behavior must be explicit. | Prevents stale or misleading views. |
| UI17 | **Tables and cards must prioritize scanability.** Use concise labels, stable alignment, and consistent status placement. | Important for operations dashboards. |
| UI18 | **Fee explainer UI is Customer- and Advisor-facing only.** Do not render the structured six-bullet fee pattern on the **Product** tab, in the **weekly pulse email** body, or other PM surfaces; Product shows pulse, themes, quotes, actions, and analytics per `Docs/UserFlow.md` and `Docs/UI.md`. | Keeps PM surfaces analytical while preserving regulated, source-backed fee chat where users expect it. |

## Latency and performance rules

| ID | Rule | Enforcement |
|---|---|---|
| L1 | **Define latency budgets per interaction type.** Track average and percentile latency, especially p95. | Averages alone are misleading. |
| L2 | **UI acknowledgment budget:** show visible feedback within 200 ms of user action. | Use spinner, skeleton, disabled state, or processing badge. |
| L3 | **Simple read endpoints target p95 under 800 ms.** | Applies to health, summaries, lists, and current status endpoints. |
| L4 | **Workflow write endpoints target p95 under 2 seconds.** | Applies to create, update, approval, booking, and send initiation flows. |
| L5 | **LLM-powered responses must show progress early.** Show first meaningful progress or an inline waiting state quickly; target completion under 8 seconds for standard chat. | Avoid dead-air UX. |
| L6 | **Long-running work must be asynchronous.** Pulse generation, email fan-out, and noncritical batch processing must not block user-facing requests. | Preserves dashboard responsiveness. |
| L7 | **Avoid serial network hops in critical paths.** Do not chain unnecessary request-to-request dependencies for user-facing actions. | Reduces tail latency. |
| L8 | **Cache stable reads where useful.** Current pulse, static configuration, reusable metadata, and reference artifacts may be cached safely. | Reduces cost and latency. |
| L9 | **Measure tail latency explicitly.** Instrument p50, p95, and p99 for important endpoints and workflow paths. | Tail latency is what users actually feel. |
| L10 | **Timeouts must be explicit.** External API calls, LLM calls, and slow fetches need clear timeout and retry policies. | Prevents hanging requests. |
| L11 | **Graceful degradation is preferred to indefinite waiting.** If a noncritical dependency is slow, return a degraded but useful result when possible. | Improves reliability perception. |
| L12 | **Polling must be bounded and stoppable.** No uncontrolled polling loops in the UI. | Prevents accidental load amplification. |
| L13 | **Do not block the main workflow on secondary enrichments.** Extras like summaries, badges, or derived metadata should not block the base action when not strictly necessary. | Keeps user-critical paths fast. |

## Data, schema, and persistence rules

| ID | Rule | Enforcement |
|---|---|---|
| D1 | **Validate all request and response boundaries.** API payloads, LLM outputs, DB writes, and integration payloads must use explicit schemas. | No unvalidated free-form objects in critical paths. |
| D2 | **Database writes must be intentional and minimal.** Store only what is required for workflow continuity, auditability, and product value. | Prevents noisy, hard-to-govern data. |
| D3 | **Enums and workflow states must be centralized.** Booking states, approval states, send states, and job states must be defined once and reused everywhere. | Prevents status drift. |
| D4 | **Migrations must be additive and safe.** Do not break existing data flows without an explicit migration path. | Supports iterative development. |
| D5 | **Persist source-of-truth timestamps consistently.** Use a standard timestamp format and document whether values are stored in UTC and displayed in IST. | Prevents time confusion. |
| D6 | **Duplicate prevention must exist at both UI and backend layers.** | Important for booking, approval, and send actions. |
| D7 | **Never persist raw secrets or OAuth tokens in plaintext.** If token persistence is required, it must be encrypted or stored using the approved secure mechanism. | Security requirement. |
| D8 | **Artifacts must be traceable.** Pulse IDs, booking IDs, session IDs, and approval records must be linkable across the workflow. | Enables auditability and debugging. |
| D9 | **Preserve lineage for ingested data.** Store or archive raw collection output where practical, then persist normalized rows with `source`, `source_id`, `ingested_at`, and `content_hash` (or equivalent) so replays and dedupe are possible. | Supports debugging Play Store DOM changes and scraper drift. |

## LLM and retrieval rules

| ID | Rule | Enforcement |
|---|---|---|
| R1 | **Grounded answers only.** If retrieval confidence is weak, the assistant must ask a clarifying question or provide a bounded fallback rather than inventing facts. | Prevents hallucinations. |
| R2 | **Retrieval and generation must remain separate concerns.** Retrieval selects context; generation uses only approved context and policy instructions. | Improves control and debuggability. |
| R3 | **Prompt context must be bounded.** Do not dump full transcripts, full review corpora, or raw records into prompts unless explicitly needed. | Controls cost and quality. |
| R4 | **LLM outputs must be schema-validated when used programmatically.** | Especially for theme extraction, summaries, and workflow actions. |
| R5 | **Refusal and uncertainty are valid outputs.** The system must be allowed to say it lacks enough evidence. | Safer than fabricated confidence. |
| R6 | **Customer-facing responses must remain informational and product-safe.** Do not imply unsupported financial advice or guaranteed outcomes. | Domain safety. |
| R7 | **Review summarization must preserve representative signal.** Do not overfit to only negative or only positive samples. | Needed for useful product intelligence. |
| R8 | **The same user intent should yield the same workflow behavior across text and voice.** | Runtime parity. |
| R9 | **Prompt templates belong in versioned, centralized files.** Do not scatter major prompts across random modules. | Easier iteration and auditing. |
| R10 | **Use Gemini 2.5 Flash by default and fallbacks intentionally.** Primary generation uses **`gemini-2.5-flash`** (`GEMINI_MODEL`). Configure **`GEMINI_API_KEY_FALLBACK`** and **`GROQ_API_KEY_FALLBACK`**; on primary-key **quota / rate limit / token exhaustion** (or equivalent provider errors), **automatically retry once** with the matching **fallback** key before failing the user request. Log **tier** (primary vs fallback) and **provider**, never key values. | Keeps the product running through key rotation and burst traffic without silent wrong-model behavior. |
| R11 | **Hybrid retrieval baseline is strongly recommended for finance Q&A.** Use sparse + dense retrieval in parallel, then fuse (for example with RRF); apply reranking when enabled by the phase implementation. | Improves recall and groundedness for mixed query styles while staying phase-compatible. |
| R12 | **Chunk by semantic sections with metadata, not naive fixed windows only.** Keep source metadata (e.g., source URL, doc type, topic, last checked) attached through retrieval and citation. | Preserves context quality and citation traceability. |
| R13 | **Disallowed intent classes must short-circuit.** Advice-seeking or unsafe/PII requests must refuse early instead of entering normal retrieval + generation. | Reduces policy and safety failures. |
| R14 | **Constrained answer templates are preferred for citation-critical outputs.** When source fidelity matters, enforce structured response shapes with explicit citation fields. | Reduces free-form hallucination and missing-source drift. |

## Workflow integrity rules

| ID | Rule | Enforcement |
|---|---|---|
| W1 | **A workflow state may only change through approved transitions.** | No ad hoc direct mutation of status values. |
| W2 | **Customer, Product, and Advisor views must agree on shared entities.** Booking IDs, pulse IDs, statuses, and timestamps must remain consistent across tabs. | Prevents cross-role mismatch. |
| W3 | **Approval-gated actions must never run before approval state is committed.** | Ensures correct sequencing. |
| W4 | **Retries must not duplicate outcomes.** | Applies to send, approve, book, cancel, and background job flows. |
| W5 | **Partial failures must preserve workflow truth.** If approval succeeds but email fails, preserve approval state and surface remediation state clearly. | Important for real operations. |
| W6 | **Manual repair paths must exist for critical failures.** Operators should be able to retry or recover important failed actions. | Operational practicality. |
| W7 | **Background jobs must be safe to rerun.** Reprocessing must not corrupt state or duplicate sends. | Necessary for scheduler reliability. |
| W8 | **No hidden side effects from read endpoints.** GET-style or read-oriented operations must not mutate business state. | Prevents surprising behavior. |
| W9 | **State transition reasons should be captured when meaningful.** Reject/cancel/fail states should include enough context for later review. | Improves auditability. |

## Integrations and external systems rules

| ID | Rule | Enforcement |
|---|---|---|
| I1 | **All external writes must pass through dedicated integration modules.** UI and domain code must not call provider SDKs directly. | Keeps concerns separated. |
| I2 | **OAuth credentials remain server-side only.** Browser code must never access privileged Google credentials or tokens. | Security requirement. |
| I3 | **Side effects must be approval-gated or explicitly user-triggered.** No uncontrolled email/calendar/sheets writes. | Prevents accidental actions. |
| I4 | **Retries must be bounded, logged, and idempotent.** | Prevents duplicate sends and events. |
| I5 | **Every integration needs graceful degradation.** If Gmail, Calendar, Sheets, or LLM services fail, the workflow should preserve truth and expose remediation state. | Reliability over perfection. |
| I6 | **Each integration must have a local mock or dev-safe path.** | Supports manual testing without real side effects when appropriate. |
| I7 | **Integration responses must be normalized.** Convert provider-specific results into internal status models before passing them deeper into the app. | Simplifies downstream logic. |
| I8 | **Provider rate limits and quotas must be respected.** | Important for Google APIs and LLM providers. |
| I9 | **MCP is a thin governed action layer, not a default runtime path.** Keep latency-sensitive live chat/voice operations on direct service integrations; use MCP for explicit governed external actions (for example, scheduler- or approval-triggered side effects). | Preserves responsiveness while retaining controlled actions where they matter. |
| I10 | **Playwright dependencies are explicit.** Declare `playwright` and browser install steps in backend or scripts `requirements`/CI; document headless flags and timeouts; fail jobs with actionable errors when selectors break. | Play Store UI changes are frequent; ops must detect breakage quickly. |

## Observability and debugging rules

| ID | Rule | Enforcement |
|---|---|---|
| O1 | **Every request must have a correlation ID.** It should flow across frontend request, backend handling, LLM calls, and integration logs where practical. | Speeds root-cause analysis. |
| O2 | **Critical workflow transitions must be logged explicitly.** Include from-state, to-state, actor or source, and reason when relevant. | Supports auditability. |
| O3 | **Measure durations around critical steps separately.** Retrieval time, LLM time, DB time, and integration time must be distinguishable. | Helps locate bottlenecks. |
| O4 | **User-visible failures must be traceable to logs.** Surfaced errors should correspond to structured backend log metadata. | Improves supportability. |
| O5 | **Do not log raw prompt contents if they may contain sensitive data.** Prefer redacted summaries, token counts, and high-level descriptors. | Privacy-preserving observability. |
| O6 | **Retry attempts must be logged distinctly from first attempts.** | Needed for diagnosing duplication and tail latency. |
| O7 | **Avoid noisy logs.** Log milestones, decisions, errors, and metrics; do not dump entire payloads unnecessarily. | Keeps signal-to-noise high. |
| O8 | **All critical jobs must emit start, success, and failure events.** | Important for scheduler, pulse generation, and outbound communication jobs. |

## Evals and quality rules

| ID | Rule | Enforcement |
|---|---|---|
| EVAL1 | **Every LLM-powered feature must have eval coverage.** Chat, retrieval, fee explanation, pulse generation, summarization, and voice parity need explicit evaluation criteria. | Prevents subjective-only validation. |
| EVAL2 | **Evaluate groundedness and relevance separately.** A response can be relevant but ungrounded, or grounded but unhelpful. | Quality must be multi-dimensional. |
| EVAL3 | **Low-confidence responses must degrade safely.** If grounding or certainty is weak, ask clarifying questions or return bounded fallback responses. | Safer than hallucinated certainty. |
| EVAL4 | **Maintain golden datasets once a phase stabilizes.** Include happy paths, edge cases, ambiguous inputs, and adversarial cases. | Supports regression control. |
| EVAL5 | **Do not evaluate only wording.** Also evaluate source selection, state transition correctness, action eligibility, policy compliance, and integration outcomes. | ProductOps quality is more than text quality. |
| EVAL6 | **Hybrid workflows need end-to-end evals.** Booking chat should be evaluated on answer quality, slot extraction, state persistence, and advisor visibility together. | Ensures whole-path correctness. |
| EVAL7 | **Failure cases must be included in eval datasets.** Empty retrieval, duplicate approval attempts, expired OAuth, malformed input, and partial integration failure must be covered. | Prevents brittle systems. |
| EVAL8 | **Track hallucination rate explicitly.** Unsupported fees, invented product details, invented sources, or fabricated states are hard failures. | Critical for trust. |
| EVAL9 | **Weekly Pulse outputs must be judged for actionability, not only readability.** Summaries must be concise, theme-faithful, and decision-useful. | Matches product stakeholder needs. |
| EVAL10 | **Voice parity must be tested.** Equivalent text and voice intents should produce equivalent downstream actions and state changes. | Keeps voice as a true adapter. |
| EVAL11 | **Eval thresholds must be documented.** Define what passing means before declaring a feature complete. | Prevents vague acceptance criteria. |
| EVAL12 | **A sampled manual review is always required.** Automated evals alone are not enough for finance-adjacent customer workflows. | Adds human judgment where it matters. |
| EVAL13 | **Evals must run on stable fixtures.** Do not let moving live data make regression results meaningless. | Ensures comparable results over time. |
| EVAL14 | **Record version context for evals.** Log model, prompt version, retrieval settings, and dataset version for every eval run. | Makes results interpretable. |

## Accessibility and content rules

| ID | Rule | Enforcement |
|---|---|---|
| A1 | **Readable typography and sufficient contrast are mandatory.** | Especially important for status-heavy dashboards. |
| A2 | **All interactive controls need accessible labels.** Icon-only buttons must include descriptive labels and, where useful, helper tooltips. | Screen-reader support. |
| A3 | **Use plain language in user-facing operational messages.** Avoid jargon like `mutation failed`, `exception`, or `internal state mismatch`. | Improves trust and usability. |
| A4 | **Status vocabulary must be standardized.** Reuse one set of approved words for pending, approved, rejected, failed, cancelled, processing, scheduled, and sent. | Reduces confusion. |
| A5 | **Generated summaries must be concise and scannable.** Favor short sections, bullets, and clear labels over dense paragraphs. | Faster operational comprehension. |
| A6 | **The UI must remain usable without hover.** Important actions and information should not depend solely on hover interactions. | Accessibility and device compatibility. |

## Cursor-specific guardrail rules

| ID | Rule | Enforcement |
|---|---|---|
| C1 | **Do not accept happy-path-only implementations.** For every generated UI or API, loading, empty, and error handling must also be implemented. | Common AI omission. |
| C2 | **Do not let Cursor silently hardcode URLs, IDs, or secrets.** Any external endpoint, calendar ID, sender email, sheet ID, model ID, or API URL must come from config. | Common AI shortcut. |
| C3 | **Do not accept vague TODOs in critical paths.** Stubs are allowed only when clearly isolated to the current phase and documented as stubs. | Keeps project state honest. |
| C4 | **Require schema validation at boundaries.** Request models, response models, LLM outputs, and DB-facing payloads must be validated explicitly. | Prevents fragile integrations. |
| C5 | **Require idempotency for every write path.** If Cursor adds create/send/approve/cancel logic, it must also define duplicate prevention. | Common operational oversight. |
| C6 | **Require instrumentation on new critical paths.** New workflow code must include logs, timing, and clear error handling from the start. | Avoids invisible failures. |
| C7 | **Require manual test instructions for each completed phase.** Cursor should leave behind a verifiable path, not just code. | Makes progress testable. |
| C8 | **Do not accept architecture-breaking convenience shortcuts.** If a shortcut moves domain logic into UI or provider logic into domain services, reject it. | Preserves long-term maintainability. |

## Phase-specific rules

### Phase 1 — Project skeleton, config, and health path

| ID | Rule | Implementation expectation |
|---|---|---|
| P1.1 | **Validate required env vars at startup.** | Missing env vars must fail fast with clear messages. |
| P1.2 | **Centralize config early.** | App config, URLs, feature flags, model IDs, and integration IDs must come from a shared settings layer. |
| P1.3 | **Create a single backend health endpoint and a single frontend connectivity check.** | The first end-to-end test proves frontend-to-backend communication. |
| P1.4 | **Safe settings serialization only.** | Logs and debug screens must never expose secrets. |
| P1.5 | **Use the documented project structure as the authority.** | Avoid ad hoc folder creation outside the planned scaffold. |
| P1.6 | **Implement dashboard shell and badges route foundation in this phase.** | Establish frontend shell and backend badges endpoint shape early. |
| P1.7 | **Supabase and local cross-origin foundations must be validated.** | Confirm DB connectivity baseline plus frontend (`localhost:3000`) to backend (`localhost:8000`) CORS/preflight behavior. |

**Definition of Done**
- Frontend boots.
- Backend boots.
- Health endpoint works.
- Frontend can call backend successfully.
- Dashboard shell foundation is present.
- Badges route foundation exists.
- Supabase connection foundation is validated.
- `.env.example` is aligned with implementation.

### Phase 2 — Weekly Pulse backend and Product tab

| ID | Rule | Implementation expectation |
|---|---|---|
| P2.1 | **Pulse generation and retrieval logic live in backend services.** | Product tab renders backend outputs; it does not own pulse business logic. |
| P2.2 | **Weekly pulse APIs must support current and history retrieval.** | Product tab can render latest pulse and prior pulse states reliably. |
| P2.3 | **Subscribe and unsubscribe paths must be explicit and safe.** | Avoid ambiguous subscription state transitions and duplicate subscriptions. |
| P2.4 | **Product tab must handle loading, empty, partial, and error states.** | No blank or brittle pulse dashboard states. |
| P2.5 | **Pulse output quality must prioritize actionability over verbosity.** | Keep PM-facing summaries concise, clear, and decision-useful. |
| P2.6 | **Groww Play Store reviews are ingested via Playwright as a documented job.** | Collect reviews up to **8 weeks** lookback only; job writes **raw** records first; failures are logged with correlation IDs. |
| P2.7 | **Mandatory pulse pipeline after raw collection.** | Do not call theme or pulse LLMs on raw Playwright payloads. Apply **cleaning** then **normalization** (dedupe, spam/low-signal filtering, PII minimization, policy filters per product spec—e.g. English-only, min length, helpfulness weighting, rating balance including **4:1** issues/improvements vs positive sentiment targets where configured) before **theme generation (Groq)** and **pulse generation (Gemini 2.5 Flash)**. Groq/Gemini must only see bounded, cleaned text. |
| P2.8 | **No PII in collected reviews.** | Do not store reviewer names, phone numbers, Aadhaar, or other PII; store **review_id** (and allowed fields such as device type) for database reference only. |

**Definition of Done**
- Pulse generation API works.
- Product tab renders current pulse.
- Pulse history is retrievable.
- Subscribe and unsubscribe flows work.
- Groww Play Store review collection and normalization path is demonstrable (manual or scheduled run).
- One full run demonstrates **cleaning → normalization → theme generation → pulse generation → persisted pulse** (or documented empty-ingestion degraded mode).

### Phase 3 — Customer text chat foundation

| ID | Rule | Implementation expectation |
|---|---|---|
| P3.1 | **Customer chat runtime must be stable in text mode first.** | Text chat must work before voice adapters are introduced. |
| P3.2 | **Prompt chips use the same validated runtime path as typed input.** | Suggestions cannot bypass request validation or policy checks. |
| P3.3 | **Chat persistence is required for session continuity.** | Messages and session context are stored and retrievable. |
| P3.4 | **Customer routing logic belongs in backend services.** | Frontend handles rendering and interaction only. |
| P3.5 | **Customer chat UI must expose honest state transitions.** | Show loading, success, fallback, and failure states clearly. |

**Definition of Done**
- Customer chat UI works.
- Users can submit text prompts and prompt chips.
- Chat sessions and messages persist.
- Customer routing skeleton is implemented in backend.

### Phase 4 — RAG and grounded hybrid Q&A

| ID | Rule | Implementation expectation |
|---|---|---|
| P4.1 | **RAG runtime must keep retrieval and generation separated.** | Retrieval selects context; generation composes only from approved context. |
| P4.2 | **Retrieval and answer generation remain separate.** | Retrieval selects context; generation uses only approved context and policy prompt. |
| P4.3 | **Grounded answers only.** | Weak context must trigger safe fallback behavior. |
| P4.4 | **MF, fee, and hybrid queries must all be supported.** | Combined prompts are answered in one coherent grounded response. |
| P4.5 | **Customer responses must remain product-safe.** | Informational tone only; no unsupported financial guidance. |
| P4.6 | **Phase 4 retrieval stack should be hybrid.** | Implement BM25 + embeddings in parallel with fusion; rerank where configured. |
| P4.7 | **Retrieval output must carry citation metadata end to end.** | Returned chunks include source identity and freshness metadata used in the final response. |
| P4.8 | **MF and fee scraped sources use normalize → chunk → index.** | No raw HTML in vector/BM25 tables; chunk boundaries and metadata are stable enough to rebuild indexes via `rebuild_index.py` after source updates. |

**Definition of Done**
- Customer chat UI works.
- Users can ask supported questions.
- Hybrid FAQ and fee-explainer retrieval works.
- Weak retrieval results lead to safe fallback behavior.
- Grounded response citations and metadata are preserved.
- At least one MF and one fee source path runs through normalization, chunking, and index rebuild documented in the runbook.
- Disclaimers are used wherever required by `Docs/ProblemStatement.md` and `Docs/UserFlow.md`.

### Phase 5 — Booking and customer workflow state

| ID | Rule | Implementation expectation |
|---|---|---|
| P5.1 | **Booking logic lives in backend domain/services, not the UI.** | Frontend renders workflow state and actions only. |
| P5.2 | **Timezone clarity is mandatory.** | All booking times are shown and confirmed in IST unless explicitly changed. |
| P5.3 | **Booking identifiers must be collision-safe.** | Every booking has a reliable unique reference. |
| P5.4 | **State transitions must be explicit.** | Requested, pending, approved, rejected, cancelled, and completed states are centrally defined. |
| P5.5 | **Cancellation and reschedule handling must be safe.** | Invalid transitions are blocked with clear feedback. |

**Definition of Done**
- Booking can be initiated from the customer flow.
- Booking state is stored.
- Booking status appears in the UI.
- Cancel flow works.
- Invalid transitions are handled gracefully.

### Phase 6 — Advisor operations and HITL approval

| ID | Rule | Implementation expectation |
|---|---|---|
| P6.1 | **Human approval is authoritative for advisor-side operational actions.** | Approval and rejection must be explicit and traceable. |
| P6.2 | **Advisor UI summarizes context rather than dumping raw payloads.** | Show concise summaries and only relevant supporting data. |
| P6.3 | **Approval actions must be idempotent.** | Double-clicks or retries must not trigger duplicate side effects. |
| P6.4 | **Advisor actions must update shared state consistently.** | Customer and advisor views stay coherent after approval changes. |
| P6.5 | **Approval and rejection must be auditable.** | Persist status, timestamp, and relevant actor context. |
| P6.6 | **Approval flow must remain compatible with later governed external actions.** | Keep side-effect triggering boundaries explicit so Phase 7 integrations can be added cleanly. |

**Definition of Done**
- Pending approvals are visible.
- Advisor can approve or reject.
- Shared state updates correctly.
- Badge counts and statuses reflect current state.

### Phase 7 — External integrations: Gmail, Calendar, Sheets, scheduler

| ID | Rule | Implementation expectation |
|---|---|---|
| P7.1 | **External writes occur only through integration services.** | No direct Gmail, Calendar, or Sheets logic in UI or domain modules. |
| P7.2 | **OAuth secrets and tokens stay server-side only.** | Browser never sees privileged credentials. |
| P7.3 | **Side effects must be approval-gated or explicitly user-triggered.** | No uncontrolled send or create behavior. |
| P7.4 | **Retries must be bounded and idempotent.** | Prevent duplicate sends, events, and sheet writes. |
| P7.5 | **Integration failures must degrade gracefully.** | Preserve workflow truth and expose actionable remediation state. |
| P7.6 | **Scheduler behavior must support both manual and automated triggering.** | Keeps recovery and testing practical. |

**Definition of Done**
- Gmail action works through the backend.
- Calendar event creation works.
- Sheets append works if enabled.
- Failure states are visible and safe.
- Scheduler endpoint can be triggered securely.

### Phase 8 — Voice and final hardening

| ID | Rule | Implementation expectation |
|---|---|---|
| P8.0 | **Do not require voice to ship Phases 1–7.** | Release and E2E acceptance use the **text-only** checklist in `Docs/Runbook.md` until voice is explicitly in scope. |
| P8.1 | **Voice reuses the exact same runtime.** | STT output becomes text input to the existing orchestration path. |
| P8.2 | **No domain logic in voice modules.** | Voice layer does not make booking or approval decisions. |
| P8.3 | **Voice and chat must show behavior parity.** | Same user intent should produce the same downstream behavior. |
| P8.4 | **Spoken outputs must be concise and unambiguous.** | Especially for times, dates, and confirmation states. |
| P8.5 | **Hardening must include degraded modes.** | LLM outages, integration failures, and slow services must have safe fallbacks. |
| P8.6 | **Voice remains an adapter over the existing text runtime.** | Voice may improve I/O only; it must not become a separate business workflow implementation. |

**Definition of Done**
- Voice input and output work.
- Voice path reuses the text runtime.
- Parity scenarios pass.
- Failure handling is user-safe and operator-friendly.

## Manual testing rule

Before closing any phase, verify at least the following:
- One happy-path manual test succeeds.
- One failure-path manual test is exercised.
- Logging for the phase is visible and useful.
- The UI reflects loading, success, and failure honestly.
- No secrets are hardcoded.
- Documentation and env examples are updated.

## Recommended latency budgets

| Interaction | Target |
|---|---|
| Button click acknowledgment | under 200 ms |
| Simple read endpoint p95 | under 800 ms |
| Workflow create or update p95 | under 2 seconds |
| Initial chat progress indicator | under 2 seconds |
| Standard LLM response completion | under 8 seconds |
| Background jobs | async; must not block the UI |

## Recommended eval dimensions

| Feature | Minimum eval dimensions |
|---|---|
| RAG chat | groundedness, relevance, fallback quality, source fidelity |
| Fee explainer | factual correctness, clarity, source support, no invented fees |
| Review / corpus ingestion | Playwright job success rate, parse coverage, normalization drop reasons, dedupe correctness, chunk/index integrity |
| Weekly Pulse | pipeline order integrity (clean → normalize → theme → pulse), theme accuracy, quote fidelity, sentiment balance, actionability |
| Booking flow | state correctness, slot parsing, duplicate prevention, recovery handling |
| Advisor approval | state transition correctness, idempotency, auditability |
| Voice | transcript quality, intent parity with text, safe fallback behavior |

## Phase completion checklist

Before closing any phase:
- [ ] Phase-specific rules are implemented.
- [ ] Definition of Done is verified manually.
- [ ] Required env vars are documented.
- [ ] Logging and error handling are present.
- [ ] No secrets are hardcoded.
- [ ] Docs reflect actual implementation.
- [ ] UI states are handled cleanly.
- [ ] Regression impact has been checked.
- [ ] Latency impact is acceptable for the phase.
- [ ] If LLM behavior was introduced or changed, eval coverage was updated.
- [ ] Before treating **Phase 7** as complete, run **`Docs/Runbook.md` → End-to-end test (text-only, before voice)** through the phases in scope (voice not required).