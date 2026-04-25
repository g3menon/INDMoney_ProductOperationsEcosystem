# INDMoney Product Operations Ecosystem — Failures and Edge Cases

This document lists the most important failures, degraded modes, and edge cases for the INDMoney Product Operations Ecosystem. It is organized by implementation phase so it can be used directly for development planning, manual testing, and regression reviews.

The goal is not to eliminate every failure, but to ensure every important failure mode has a designed response. Modern failure-mode analysis emphasizes identifying degraded states, isolating failure impact, and keeping the end-to-end flow usable even when one component is unavailable or slow.[1][2]

## How to use this file

- Treat each item as a scenario that should have an expected system behavior.
- For each phase, cover both the happy path and the listed failure/edge cases before marking the phase complete.
- When a feature is intentionally deferred, define the user-visible fallback rather than leaving behavior undefined.
- Prefer graceful degradation over total failure wherever possible.[1][2]

## Global failure principles

These principles apply to all phases:

- A component failure should not automatically become a system-wide failure if the core user workflow can still continue in degraded mode.[1][2]
- Every major screen should support blank, loading, partial, error, and ideal states rather than assuming ideal data conditions only.[3][4]
- Boundary values, malformed inputs, and incomplete data must be treated as first-class test cases because edge-case testing is most effective when it targets data integrity, UX damage, and workflow breakage early.[5]
- Authentication and OAuth-related flows require special attention to token expiry, redirect mismatches, incorrect scopes, and provider-side failures because these paths can block critical workflows completely.[6][7]

***

## Phase 1 — Project skeleton, config, and health path

### Main failure themes
- Project does not boot consistently.
- Configuration is incomplete or invalid.
- Frontend and backend cannot communicate.
- Local and deployed environments behave differently.

### Failures and edge cases

| Scenario | Example | Expected behavior |
|---|---|---|
| Missing required env var | `SUPABASE_URL` or `GOOGLE_CLIENT_ID` not set | App should fail fast at startup with a clear config error; it must not partially boot with undefined behavior. |
| Invalid env var format | malformed URL, empty API base URL, invalid JSON config | Startup validation should reject the config and explain the invalid field. |
| Frontend points to wrong backend | `NEXT_PUBLIC_API_BASE_URL` points to wrong domain or localhost in production | UI should show connectivity failure clearly; backend calls should not fail silently. |
| Backend boots but health check fails | app imports successfully but DB or provider dependency is unavailable | Health endpoint should distinguish between `healthy`, `degraded`, and `unavailable` if supported. |
| CORS mismatch | frontend origin not allowed by backend | Browser requests should fail visibly; developer-facing logs should identify origin mismatch quickly. |
| Port mismatch in local setup | frontend expects backend on 8000, backend runs elsewhere | Frontend should surface network error; setup docs should make the expected port explicit. |
| Inconsistent local vs production env behavior | feature works locally but fails on Render/Vercel | Config values should be environment-specific and documented; no hardcoded localhost fallbacks in production. |
| Secret accidentally logged | startup logs print env contents | Logs must redact sensitive values by default. |
| Partial boot | server starts but important routes fail after first request | Fail startup checks early instead of allowing a false healthy state. |

### Manual checks for this phase
- Start backend with one env var intentionally missing.
- Start frontend with a wrong API base URL.
- Verify health endpoint response when dependencies are unavailable.
- Verify secrets are not printed in logs.

***

## Phase 2 — Dashboard shell and role tabs

### Main failure themes
- UI renders only the happy path.
- Empty and partial states are not designed.
- Tabs drift into inconsistent patterns.
- Mock data assumptions break real integration later.

### Failures and edge cases

| Scenario | Example | Expected behavior |
|---|---|---|
| Empty data on first load | no bookings, no pulse history, no pending approvals | Show informative empty states with the next expected action instead of blank sections.[8][4] |
| One tab loads, another fails | Product tab works, Advisor tab API fails | Dashboard should show partial success rather than a full-page crash.[3] |
| Very slow tab response | one panel takes several seconds | Show loading skeleton or inline loading state quickly; user should know the app is working.[4] |
| UI renders null or partial fields | missing quote text, missing theme title, missing timestamp | Render fallback labels like `Unavailable` or hide optional sections safely; never crash on undefined values.[9] |
| Long labels or large counts break layout | large badge values, long error messages | Layout should wrap or truncate gracefully; no overlap or overflow. |
| Repeated click on tab or reload | rapid switching between tabs | UI should remain stable without duplicate requests or visual jitter. |
| Stale mock assumptions | mocked payload shape differs from backend response | Shared schemas or typed contracts should catch mismatches early. |
| Error state with no recovery | network fails once and user cannot retry | Error state should allow retry or refresh. |
| Keyboard-only navigation fails | tabs work only with mouse | Core navigation should remain keyboard accessible. |

### Manual checks for this phase
- Load the dashboard with no data in all tabs.
- Break one tab endpoint and confirm the others still render.
- Test tab navigation with keyboard only.
- Test long strings, zero values, and null fields.

***

## Phase 3 — Product pulse foundation

### Main failure themes
- Review ingestion is noisy or incomplete.
- LLM output is malformed or too expensive.
- Product insights are misleading, unbalanced, or duplicate-heavy.
- Background processing blocks the UI.

### Failures and edge cases

| Scenario | Example | Expected behavior |
|---|---|---|
| No reviews available | empty source file, failed ingestion, empty date range | Product tab should show `No pulse available yet` and explain whether ingestion failed or there is simply no data. |
| Reviews contain duplicated content | repeated app-store complaints copied many times | Deduplication or weighting logic should reduce overcounting where designed. |
| Reviews contain spam or nonsense | emoji-only, abusive text, very short text | Cleaning layer should exclude or downgrade low-signal entries before summarization. |
| LLM returns malformed JSON/schema | missing fields in theme clusters or summary object | Response should fail validation and trigger retry/fallback rather than storing corrupt output. |
| LLM overfocuses on negatives | a few angry reviews dominate the pulse | System should preserve sentiment balance and avoid misleading product conclusions. |
| LLM invents themes not supported by source reviews | unsupported recommendation appears in pulse | Output should fail eval or manual review criteria; unsupported claims must not be persisted as truth. |
| One large review batch causes high latency | thousands of reviews processed synchronously | Long-running generation must be asynchronous or paginated to avoid blocking user interaction. |
| Quotes include sensitive or irrelevant content | PII or extreme profanity included in pulse | Quote selection should sanitize or exclude unsafe excerpts before display/export. |
| Same pulse generated twice | duplicate cron or repeated click | Pulse creation should be idempotent or version-aware to avoid duplicate records. |
| Subscription state is inconsistent | user unsubscribes but still appears active | Source-of-truth subscription state should be read consistently before send actions. |
| History loads partially | latest pulse available but history query fails | Current pulse can render while history shows localized error/empty state. |

### Manual checks for this phase
- Test with zero reviews.
- Test with noisy, duplicated, and malformed review samples.
- Force malformed LLM output and confirm validation catches it.
- Trigger generate twice and confirm duplicate handling.

***

## Phase 4 — Customer chat and RAG foundation

### Main failure themes
- Retrieval is weak or mismatched.
- LLM answers are ungrounded.
- Hybrid queries behave inconsistently.
- Chat state is lost or corrupted.

### Failures and edge cases

| Scenario | Example | Expected behavior |
|---|---|---|
| No retrieval hit | user asks a question not covered by indexed sources | Assistant should say it lacks enough context and either ask for clarification or redirect safely. |
| Low-quality retrieval hit | semantically similar but wrong answer chunk retrieved | Answer layer should remain bounded by retrieved context and avoid false confidence. |
| Hybrid question spans multiple domains | user asks about both a mutual fund FAQ and fee issue in one message | System should either answer both with grounded support or clarify scope if context is incomplete. |
| User asks ambiguous question | `charges?`, `why so much?`, `this fee?` | Assistant should ask a clarifying question rather than guessing. |
| Query is too long | pasted paragraph, screenshot transcript, or long complaint | System should truncate, summarize, or pre-process safely without crashing or exceeding prompt budgets. |
| Conversation state resets unexpectedly | refresh loses chat history | If persistence is designed, session history should reload; if not, UI should state the limitation clearly. |
| Prompt suggestions bypass runtime checks | clicking a chip skips validation or source retrieval | Suggested prompts must go through the same processing path as typed input. |
| Retrieved content is stale or incomplete | data source changed but index not rebuilt | Assistant should not overstate certainty; operational docs should flag index refresh needs. |
| Unsupported financial advice request | user asks for recommendation rather than explanation | Assistant should stay informational and refuse unsupported advisory behavior. |
| LLM answers without evidence | model hallucinates fees or policies | Eval and runtime rules should treat unsupported claims as failures. |
| Chat works but source attribution is broken | response content okay, citations absent or source cards missing | UI should still show the answer, but source rendering failure should be visible and logged. |

### Manual checks for this phase
- Ask unsupported questions.
- Ask ambiguous questions.
- Ask mixed-domain questions.
- Simulate weak retrieval and verify safe fallback.
- Refresh during a session and inspect history behavior.

***

## Phase 5 — Booking and customer workflow state

### Main failure themes
- State transitions become invalid.
- Booking data is incomplete or inconsistent.
- Duplicate or conflicting bookings are created.
- Timezone confusion leads to wrong confirmations.

### Failures and edge cases

| Scenario | Example | Expected behavior |
|---|---|---|
| Missing required booking detail | user never provides name, date, contact, or issue summary | Workflow should ask only for the missing required fields and not proceed prematurely. |
| Invalid date/time input | past date, malformed date, impossible slot | System should reject with clear correction guidance. |
| Timezone ambiguity | user gives a time without timezone, system stores in wrong zone | UI and backend should normalize display/storage and confirm timezone explicitly. |
| Duplicate booking submission | double-click submit, retry after timeout | Backend must prevent duplicate booking creation or detect equivalent repeat requests. |
| Booking created but UI not updated | DB write succeeds, frontend state stale | UI should refresh, poll, or reconcile state after successful booking creation. |
| Booking ID collision | rare but possible if ID generation weak | ID strategy must be collision-safe or DB-constrained. |
| Cancel request for non-existent booking | mistyped ID | System should return safe, user-readable error. |
| Cancel request for already cancelled booking | duplicate cancellation | Operation should be idempotent and explain current state. |
| Reschedule/cancel on non-permitted state | trying to cancel after final completion | Transition should be blocked with explicit reason. |
| Partial booking created | one required field stored as null unexpectedly | Validation must prevent incomplete persistence unless drafts are explicitly supported. |
| User abandons flow midway | closes tab after two steps | System should either save draft state intentionally or expire the incomplete attempt cleanly. |
| Slot conflict emerges later | two customers reserve same advisor slot before approval path resolves | Final approval step should validate slot availability again if that is part of the workflow. |

### Manual checks for this phase
- Submit incomplete booking data.
- Submit impossible dates and past dates.
- Double-submit the same booking.
- Cancel invalid, duplicate, and already-closed bookings.
- Verify timezone display in every booking message.

***

## Phase 6 — Advisor operations and HITL approval

### Main failure themes
- Pending items are incomplete or stale.
- Approval state is inconsistent across tabs.
- Double actions create duplicate side effects.
- Advisors lack enough context to act safely.

### Failures and edge cases

| Scenario | Example | Expected behavior |
|---|---|---|
| Pending approval missing critical context | advisor sees booking but not enough summary to decide | Advisor UI should show a clear `missing context` state or fetch fallback details. |
| Same booking shown twice | duplicate pending records or stale queries | Advisor list should deduplicate or clearly reflect versions/status. |
| Approve clicked twice | network lag causes repeated action | Backend approval endpoint must be idempotent. |
| Approve succeeds, UI still shows pending | stale frontend state | UI must refresh state after mutation and show confirmation. |
| Reject path lacks reason capture | advisor rejects but no useful explanation recorded | If reason capture is required, UI should enforce or encourage it. |
| Customer and advisor tabs disagree | advisor sees approved, customer still sees pending | Shared state should reconcile from the backend source of truth. |
| Concurrent advisor actions | two operators act on the same request near-simultaneously | Backend should enforce single valid terminal transition. |
| Large queue size | many pending approvals | UI should remain usable with pagination, sorting, or virtualization if needed. |
| Stale queue item | item already processed but still visible due to delayed refresh | UI should refresh or poll appropriately; stale actions should fail safely if clicked. |
| Partial context service failure | booking exists but fee summary fetch fails | Advisor can still view and act on the base item while the missing panel shows localized error. |

### Manual checks for this phase
- Approve the same item twice.
- Reject with and without reason.
- Open the same pending item in two tabs and act from both.
- Verify customer and advisor views after approval/rejection.

***

## Phase 7 — External integrations: Gmail, Calendar, Sheets, scheduler

### Main failure themes
- OAuth flow is brittle.
- Provider-side failures break user workflows.
- Duplicate side effects occur.
- Scheduled jobs and manual triggers conflict.

### Failures and edge cases

| Scenario | Example | Expected behavior |
|---|---|---|
| OAuth redirect URI mismatch | local callback configured, production callback missing | Flow should fail explicitly with actionable setup guidance; docs should list both local and production URIs.[6] |
| Missing or incorrect OAuth scopes | Gmail works, Calendar fails due to missing scope | Integration status should surface precise missing-scope problem.[6][7] |
| Expired access token | token expired during send or event creation | Backend should refresh if supported or require re-auth cleanly.[6] |
| Expired or revoked refresh token | previously connected account stops working | UI should show `Reconnect Google account` rather than generic failure.[6] |
| Wrong authorized user connected | wrong Gmail account or personal account used | Show connected account identity clearly and allow disconnect/reconnect. |
| Google provider outage or quota exhaustion | Gmail/Calendar API unavailable | Preserve workflow truth, log provider failure, and expose a retryable remediation state. |
| Email send succeeds but DB status write fails | external action complete, internal record stale | Retry status persistence or flag reconciliation needed; avoid resending blindly. |
| Calendar event created twice | retry after timeout creates duplicate event | Use idempotency keys or internal mapping to prevent duplicate events. |
| Sheets append partially fails | row write times out after provider accepted request | Reconciliation logic should avoid duplicate appends on retry when possible. |
| Scheduler triggered twice | cron and manual trigger overlap | Job locking or idempotent job keys should prevent duplicate pulse sends. |
| Secret mismatch on internal scheduler endpoint | GitHub Actions secret wrong or missing | Endpoint should reject with clear unauthorized behavior and log enough for debugging. |
| Integration succeeds but user never sees success | action completed on provider, UI remained stale | Backend response and frontend refresh should reconcile quickly. |
| Long-running send blocks UI | bulk pulse send executed synchronously | Sending should be async or queued; UI should show queued/progress state. |
| OAuth consent not approved for user | app in testing mode excludes account | Error should explain test-user/consent limitation rather than failing ambiguously. |

### Manual checks for this phase
- Test wrong redirect URI.
- Test missing scope behavior.
- Test expired/revoked token path.
- Trigger the scheduler twice.
- Verify duplicate protection for email/calendar/sheet actions.

***

## Phase 8 — Voice and final hardening

### Main failure themes
- Voice path diverges from text path.
- STT/TTS quality causes wrong actions.
- Slow or failed voice services degrade the experience badly.
- Final regression misses cross-feature breakage.

### Failures and edge cases

| Scenario | Example | Expected behavior |
|---|---|---|
| STT transcript is wrong | accents, background noise, code-mixed input | User should be able to review/correct transcript before committing critical actions. |
| Empty or very short audio | accidental recording, muted mic | System should reject safely and prompt for retry. |
| Very long audio input | user records multi-minute monologue | System should cap, segment, or summarize safely rather than hanging indefinitely. |
| Voice path triggers different behavior than text | same request works in text but not in voice | Voice must route into the same orchestration path and be parity-tested. |
| TTS fails after valid response generated | answer exists but cannot be spoken | UI should still show text response and expose audio failure separately. |
| Slow STT/TTS provider response | voice feels frozen | Show explicit processing state and allow cancel/retry if possible. |
| Misheard dates or times | `fifteen` heard as `fifty`, `tomorrow 2` heard incorrectly | Confirmation step should restate sensitive booking details before committing. |
| Browser audio permission denied | microphone blocked | UI should provide recovery steps instead of generic failure. |
| Mobile/browser compatibility issue | recording works in one browser, fails in another | Feature should degrade to text-first fallback. |
| Voice and chat logs become inconsistent | transcript saved differently from displayed text | Store canonical text input after normalization to avoid split histories. |

### Manual checks for this phase
- Test empty audio, noisy audio, and long audio.
- Verify transcript correction path.
- Compare identical voice and text intents.
- Deny microphone permission and inspect fallback UX.

***

## Cross-phase failures that can appear anytime

These are not limited to one phase and should be considered throughout implementation.

### Data consistency failures

| Scenario | Expected behavior |
|---|---|
| Shared entity status differs across customer/product/advisor surfaces | Backend source of truth should win; UI should refresh and reconcile visibly. |
| Old cached data overwrites newer state | Use timestamps, version fields, or mutation ordering to avoid stale overwrites. |
| Concurrent updates from two surfaces | Reject invalid transitions and return current true state. |

### Security and auth failures

| Scenario | Expected behavior |
|---|---|
| Secrets accidentally committed | Rotate immediately, remove from code, and update `.env.example` safely. |
| Unauthorized internal endpoint access | Reject with 401/403 and log safely without leaking secret values. |
| Overly broad OAuth scopes | Restrict scopes to only what the feature actually needs.[7] |

### Latency and resilience failures

| Scenario | Expected behavior |
|---|---|
| One dependency becomes slow but not fully down | Degrade that feature rather than freezing the whole workflow.[1][2] |
| Retry storm after transient failure | Use bounded retries with backoff and idempotency controls.[2][10] |
| Large payload inflates prompt/token cost | Truncate, summarize, or reject with guidance rather than sending unbounded context. |

### UI integrity failures

| Scenario | Expected behavior |
|---|---|
| Loading spinner never resolves | Timeout, surface localized error, and allow retry. |
| Success state shown before backend confirmation | Use pending/processing state until backend confirms. |
| Hidden partial state | Show which panel or action succeeded versus which failed.[3] |

***

## Suggested minimum failure test pack

Before final submission, the project should at minimum be tested against these scenarios:

1. Missing env var at startup.
2. Wrong frontend API base URL.
3. Empty dashboard state for all tabs.
4. Product pulse generation with zero reviews.
5. Malformed LLM output for pulse generation.
6. Unsupported customer question with weak retrieval.
7. Ambiguous customer question requiring clarification.
8. Duplicate booking submission.
9. Invalid booking cancellation.
10. Duplicate advisor approval action.
11. OAuth redirect mismatch.
12. Expired Google token.
13. Duplicate scheduler trigger.
14. Voice transcript error before booking confirmation.
15. One integration panel failing while the rest of the dashboard remains usable.

## Recommended way to use these during development

For each phase:
- Pick 3 to 5 high-impact failure scenarios first.
- Implement the system response deliberately.
- Add one manual test note for each scenario.
- Re-run the previous phase’s critical failures before closing the next phase.

This aligns with edge-case testing guidance that recommends prioritizing failure modes based on user harm, data integrity risk, and how likely they are to break core workflows.[5][11]