# Architecture

## Project overview

This project is the **Groww Product Operations Ecosystem**: a single integrated product-operations dashboard for Groww-related workflows. It combines capabilities inspired by three earlier projects:

- **M1:** FAQ / RAG-style mutual fund assistance
- **M2:** Weekly Pulse / review intelligence / issue extraction
- **M3:** AI appointment scheduling with voice and Google integrations

The final system is **not** a merger of old repos. It is a **new integrated product** built in one repo, with selected logic patterns and modules ported from the previous projects.

## Core product goal

Build a single dashboard with **3 tabs**:

- **Customer**
- **Product**
- **Advisor**

The dashboard should support:

- grounded mutual fund and fee-related Q&A
- hybrid queries that combine multiple intents
- booking and cancellation flows
- weekly pulse generation and subscription
- advisor approval workflows
- booking-related analytics
- optional voice support
- governed Google actions via OAuth-backed integrations

## Locked decisions

- Use **one repo**
- **Groww Google Play Store** reviews are collected using the **Playwright** library against the public Play Store listing (Android package `com.nextbillion.groww`; canonical listing URL is recorded in `Deliverables/Resources.md`). Collection runs **server-side or in batch jobs** (not in the browser bundle); respect Play Store terms, rate limits, and robots policies in implementation.
- **Mutual fund** and **fee explainer** pages are ingested via approved **web scraping** pipelines (separate from Play Store review collection), with the same **normalization → chunking → indexing** discipline as other text sources.
- Frontend: **Next.js + TypeScript + Tailwind + shadcn/ui**
- Backend: **FastAPI (Python)**
- Frontend deployment: **Vercel**
- Backend deployment: **Render**
- Primary database / source of truth: **Supabase Postgres**
- Google auth model: **Google OAuth only**
- **No Google service account**
- Gmail actions for weekly pulse and for confirmation emails use **Google OAuth**
- Google Calendar actions use **Google OAuth**
- Google Sheets access, if needed, also uses **Google OAuth**
- Scheduler: **GitHub Actions**
- LLM split:
  - **Groq** for token-heavy preprocessing / cleanup
  - **Gemini** for synthesis / final answer generation, using **`gemini-2.5-flash`** as the default generation model unless overridden by config (see environment variables).
- **Provider resilience:** configure a **primary** and **fallback** API key for both Gemini and Groq. The backend **must** automatically switch to the configured fallback when the primary returns rate-limit / quota / billing-related errors (or other key-specific failures), and must log which key tier was used—without printing secret values.
- MCP is **lightweight**, used only for governed external actions
- Business logic lives in **FastAPI**, not in the frontend
- Google Sheets is **not** a source of truth; it is only a downstream operational/export surface if needed
- **Canonical URLs and scraping rules** (Groww Play Store, MF fund pages, fee fields, reference UI links) live in **`Deliverables/Resources.md`**; implementation docs must not duplicate divergent URL lists.

---

## Why this architecture

This architecture is optimized for:

- Python-first development speed
- fast implementation in Cursor
- clean modularity for debugging
- single-source-of-truth backend state
- minimal cross-system drift
- ability to reuse concepts from M1, M2, and M3 without inheriting their repo complexity

This architecture is also appropriate because:

- Google OAuth web-server flow works well for FastAPI backends that can securely store secrets and refresh tokens
- FastAPI supports modular multi-file application design
- Supabase cleanly separates frontend-safe keys from backend-only elevated keys

---

## High-level system architecture

```text
Browser
  |
  v
Next.js Frontend (Vercel)
  |
  |-- Dashboard Shell
  |-- Customer Tab
  |-- Product Tab
  |-- Advisor Tab
  |-- Badge UI
  |
  v
FastAPI Backend (Render)
  |
  |-- API Routers
  |-- Service / Workflow Layer
  |-- Repository Layer
  |-- RAG Engine
  |-- Booking Engine
  |-- Pulse Engine
  |-- Approval Engine
  |-- Badge Engine
  |-- LLM Router
  |-- Google OAuth / Token Management
  |-- Google API Integration Layer
  |-- Light MCP Action Layer
  |
  +--> Supabase Postgres
  +--> Gmail API
  +--> Google Calendar API
  +--> Google Sheets API
  +--> Google STT/TTS (optional, later phase)
  +--> GitHub Actions Scheduler Webhook
  +--> Groww Play Store (Playwright collection jobs)
```

Scheduled or manual jobs use **Playwright** to fetch Play Store reviews; scraped MF/fee pages follow separate collectors. Both paths feed **normalization** before chunking or pulse preprocessing.

## Product surfaces

### 1. Customer tab

**Purpose:**

- help the customer ask mutual fund and fee-related questions
- support hybrid queries
- support booking and cancellation
- support chat history
- optionally support voice

**Main features:**

- text chat input
- prompt suggestion chips
- chat history
- grounded mutual fund Q&A
- fee explanation Q&A
- hybrid Q&A
- appointment booking
- booking ID generation
- booking cancellation by booking ID
- optional voice transcript input
- optional TTS response playback

### 2. Product tab

**Purpose:**

- help the PM understand current issues and distribute Weekly Pulse

**Main features:**

- latest weekly pulse
- pulse history
- subscription / unsubscribe
- send status
- booking issue analytics
- ability to view the csv of the data displayed on pulse and download it
- Monday 10 a.m. IST weekly send workflow
- **No structured fee-explainer tutorial** (e.g. the customer six-bullet fee pattern) on the Product tab or inside the **weekly pulse email** body; those patterns are **Customer** and **Advisor** surfaces only, per `Docs/UserFlow.md` and `Docs/UI.md`.

### 3. Advisor tab

**Purpose:**

- help advisors review booking context and approve / reject next actions

**Main features:**

- pending approvals
- upcoming slots
- booking summary preview
- booking ID visibility
- approve / reject actions
- confirmation status visibility

## User flows (authoritative product behavior)

Synthesized from `Docs/UserFlow.md`. The tab feature lists above describe *what* the UI offers; this section describes *how* the product must behave for PMs, customers, and advisors.

### Product (PM) flow

- A PM opens the dashboard and can **subscribe** to the weekly pulse email.
- The **same pulse** is shown on the dashboard; on subscribe, the user should receive the **current** pulse and then **recurring** weekly pulses every **Monday 10:00 IST**.
- The dashboard must show **clear feedback** when the user subscribes (e.g. confirmation, next send time, and send/health status).
- The Product area should surface **issue analytics** for the main reasons customers **book advisor sessions** (derived from **chat/booking** context—e.g. themes in the pre-booking chat or booking metadata—not from Google Sheets as a source of truth). Align analytics with the **“voice / chat brief”** context that informs advisor outreach where applicable.
- **Fee explainer scope:** PM-facing pulse and email content focuses on **themes, quotes, actions, and downloadables**—not the customer-style **fee Q&A** pattern. If a link to the live dashboard is included in email, it is for **pulse and operations context**, not to replace **Customer** fee chat.

### Customer flow

- The customer can **type**, use **suggested prompt chips**, and (when enabled) use **voice**; these are **not mutually exclusive** in a session.
- The assistant answers **grounded** mutual fund and **fee** questions, including **hybrid** prompts that combine both, and can **book** or **cancel** appointments (cancellation by **booking ID**).
- **Prompt chips** may be MF- or **source list**–driven, or may **reflect Weekly Pulse inferences** (e.g. trending issues) to help users book for those themes.
- **Chat history** is available; **hybrid** questions must be answered **in full** (every part).
- When booking completes, the user receives a **copyable** **booking ID** in chat.
- The **customer confirmation email** (and other governed “confirmation” side effects) must run only after **advisor approval** in the **Advisor** tab flow.

### Advisor flow

- The advisor **approves** or **rejects** the booking-related workflow; the customer gets the **booking confirmation email** only **after** approval.
- The advisor view shows **pending** items and **upcoming** slots, with visible **booking IDs** for work booked from the **Customer** path.
- Each pending/upcoming item should show a **summary of the customer’s prior chat** so the advisor has context.
- The advisor can review a **proposed confirmation** (including **booking ID** and a **summary of the conversation** before the appointment) when the product surfaces those previews.
- **Fee explainer on Advisor surfaces:** structured fee explanations (same **six-bullet**, source-backed pattern as Customer when used) appear **only** in advisor-facing contexts tied to **booking / confirmation review** (e.g. proposed email body, fee notes derived from the customer’s questions)—not as a general PM dashboard widget.

---

## Architectural principles

### 1. One repo, modular boundaries

Do not split into separate repos.

Use a single repo with strict boundaries:

- frontend UI boundary
- backend API boundary
- service / workflow boundary
- repository / persistence boundary
- integration boundary

### 2. Backend owns business logic

All meaningful product logic belongs in FastAPI:

- intent routing
- booking workflow
- pulse generation
- hybrid answer composition
- approval flows
- Google action triggering
- badge computation
- analytics aggregation

Frontend should only:

- render UI
- manage view state
- call typed backend APIs
- show results, loading, and errors

### 3. Supabase Postgres is source of truth

All core state must live in Supabase Postgres:

- sessions
- chats
- pulses
- subscriptions
- bookings
- approvals
- analytics artifacts
- logs

Google Sheets, if used, is a **projection/export**, not authoritative state.

### 4. Google OAuth only

No service account will be used.

All Google integrations will authenticate via **Google OAuth web-server flow** through FastAPI.

This means:

- user authorizes once
- backend stores refresh token securely
- backend refreshes access tokens when needed
- backend uses access tokens to call Gmail / Calendar / Sheets APIs

### 5. Light MCP only

MCP is not the app runtime.

MCP is only a thin governed action layer for:

- send weekly pulse email
- send booking confirmation
- create calendar hold
- append advisor export row to Google Sheets
- fetch latest pulse context
- fetch booking summary

Do not use MCP for:

- raw DB queries
- core routing
- local workflow logic
- badge computation
- intent classification

### 6. Incremental build

Build in phases.

Do not scaffold every later-phase file immediately.

Create stable folder structure early, but implement only what is needed per phase.

---

## LLM task split

### Groq responsibilities

Use Groq for:

- preprocessing raw review text
- cleanup and normalization
- theme extraction first pass
- transcript cleanup
- first-pass summarization
- token-heavy cheap transformations

### Gemini responsibilities

Use **Gemini 2.5 Flash** (`gemini-2.5-flash` via `GEMINI_MODEL` or equivalent settings) for:

- final weekly pulse synthesis
- quote selection logic if model-based
- final response composition
- hybrid answer composition
- advisor-friendly summaries
- booking summaries
- polished explanation output

### Rule

Prefer deterministic logic first.

Use LLMs only where they add meaningful product value.

### API keys, quotas, and fallbacks

- Store **`GEMINI_API_KEY`** (primary) and **`GEMINI_API_KEY_FALLBACK`**; store **`GROQ_API_KEY`** (primary) and **`GROQ_API_KEY_FALLBACK`**.
- On **429**, **resource exhausted**, **quota**, or **billing** errors from the primary key—or when the application detects **token budget exhaustion** for a given call—**retry the same logical request once** using the **fallback** key for that provider before surfacing a user-visible failure.
- If **both** keys fail for a provider, degrade gracefully (cached pulse, safe chat fallback, or explicit “try again later”) and log structured error metadata **without** logging key material.
- Record in observability which **tier** (primary vs fallback) succeeded for post-incident analysis.

---

## Backend architecture

Use a modular FastAPI application structured by features and services.

### Layered structure

```text
Router Layer
   ↓
Service / Workflow Layer
   ↓
Repository Layer
   ↓
Database + External Integrations
```

### Router layer

**Responsibilities:**

- define endpoints
- validate request/response shapes
- call services
- return standard API envelopes
- no heavy business logic

**Routers:**

- health
- dashboard
- pulse
- chat
- booking
- advisor
- approval
- voice
- internal
- auth
- evals

### Service / workflow layer

**Responsibilities:**

- orchestration
- decision-making
- state transitions
- composition of internal and external actions

**Key services:**

- `customer_router_service`
- `pulse_workflow_service`
- `booking_workflow_service`
- `approval_workflow_service`
- `badge_service`
- `scheduler_service`
- `advisor_context_service`
- `google_oauth_service`
- `prompt_service`

### Repository layer

**Responsibilities:**

- isolate DB reads/writes
- keep SQL/query logic out of services
- keep data access testable

**Repositories:**

- `pulse_repository`
- `chat_repository`
- `booking_repository`
- `approval_repository`
- `analytics_repository`
- `subscription_repository`
- `token_repository`
- `log_repository`

### Integration layer

**Responsibilities:**

- external API wrappers only
- no product logic

**Integrations:**

- supabase client
- gmail client
- calendar client
- sheets client
- stt client
- tts client
- groq client
- gemini client

---

## Google OAuth architecture

### Decision

Use Google OAuth only, without a service account.

### Why

This app acts on behalf of a single Google account for:

- Gmail sending
- Calendar event creation
- Google Sheets row append

This fits the Google OAuth web-server flow.

### Flow

```text
Admin / project owner authorizes Google account once
    ↓
FastAPI receives auth code at callback route
    ↓
FastAPI exchanges auth code for:
- access token
- refresh token
    ↓
FastAPI securely stores tokens
    ↓
Whenever Gmail / Calendar / Sheets action is needed:
- check token validity
- refresh if expired
- use access token to call Google API
```

### Important rules

- request offline access to obtain refresh token
- store refresh token securely
- never expose Google client secret to frontend
- never call Gmail / Calendar / Sheets directly from frontend
- keep all Google API actions backend-only

### Google scopes expected

**Identity:**

- `openid`
- `email`
- `profile`

**Gmail:**

- `https://www.googleapis.com/auth/gmail.send`

**Calendar:**

- `https://www.googleapis.com/auth/calendar.events`

**Sheets:**

- `https://www.googleapis.com/auth/spreadsheets`

### OAuth endpoints

**Backend auth endpoints:**

- `GET /api/v1/auth/google/login`
- `GET /api/v1/auth/google/callback`
- `POST /api/v1/auth/google/refresh`
- `POST /api/v1/auth/google/disconnect`

### Token storage

Store Google OAuth tokens in backend persistence.

**Suggested table:** `google_oauth_tokens`

**Suggested fields:**

- `id`
- `provider`
- `google_email`
- `access_token`
- `refresh_token`
- `scope`
- `token_type`
- `expires_at`
- `created_at`
- `updated_at`

If needed, encrypt stored refresh token at rest.

---

## MCP architecture

### Allowed MCP actions

- `send_weekly_pulse_email`
- `send_booking_confirmation`
- `create_calendar_hold`
- `append_advisor_sheet_row`
- `get_latest_pulse_context`
- `get_booking_summary`

### MCP design rule

Each MCP action should be:

- small
- explicit
- idempotent where possible
- easy to log and debug

### MCP responsibility boundary

MCP should do:

- governed side effects
- structured external actions

MCP should not do:

- app orchestration
- chat routing
- booking state machine
- analytics
- DB business logic

---

## RAG / knowledge architecture

### Purpose

Support:

- mutual fund factual queries
- fee explanation queries
- hybrid queries combining both

### Retrieval pipeline

```text
Source manifest
   ↓
source collection
   - Groww Play Store reviews: Playwright → raw review records
   - MF / fee sites: approved scrapers or downloads → raw documents
   ↓
persist raw artifacts (optional but recommended for reproducibility)
   ↓
normalization layer
   - canonical text encoding, whitespace/HTML cleanup
   - dedupe (URL + content hash, near-duplicate collapse where configured)
   - metadata extraction (title, section, effective date, source URL)
   - policy filters (spam, empty, off-topic) and PII minimization
   ↓
chunking (semantic sections where possible; bounded max size)
   ↓
BM25 indexing
   ↓
embedding indexing
   ↓
fusion
   ↓
optional rerank
   ↓
answer composition
```

**Corpus split:** by default **Groww Play Store** reviews feed **Weekly Pulse** and Product analytics after collection and normalization (and optional segmentation for long text). **MF and fee explainer** scraped or imported documents feed the **customer RAG** indexes. Do not merge Play Store reviews into MF/fee RAG unless you add an explicit, documented product scope and evals for that mix.

### Components

- collect (Playwright Play Store, scrapers, or file-based imports)
- normalize (dedupe, cleanup, schema mapping, policy filters)
- ingest (write normalized sources and lineage into persistence)
- chunk
- bm25
- embeddings
- fusion
- rerank
- retrieve
- answer

### Groww Play Store reviews (Playwright)

- Implement collection as a **dedicated job or script** (for example under `scripts/`) using **Playwright** to load the listing and extract review text, rating, date, and review id where available.
- Persist **raw** responses or parsed rows before normalization so ingestion can be replayed or diffed when the Play Store UI changes.
- Run the **normalization layer** before pulse preprocessing or any downstream analytics: dedupe, strip boilerplate, handle multilingual text, and downgrade obvious spam.
- **Chunking** for reviews is primarily for **pulse / theme extraction** (segmenting long threads or concatenated batches), not necessarily the same chunk boundaries as MF RAG chunks; document which path uses which chunk policy.

### Scraped MF and fee explainer documents

- After fetch, apply the **same normalization layer** (cleanup, metadata, dedupe) before **chunking** and dual indexing (BM25 + embeddings).
- MF and fee chunks must retain **citation metadata** (`source_url`, `last_checked`, `doc_type`) end to end through retrieval.

### Hybrid query behavior

If user asks a combined question:

- retrieve MF context
- retrieve fee context
- compose one structured response that answers both

### Source management

Maintain a source manifest file:

- source name
- source type
- source location
- status
- ingestion timestamp

---

## Booking architecture

### Booking states

- `draft`
- `collecting_details`
- `pending_advisor_approval`
- `approved`
- `confirmation_sent`
- `cancelled`
- `rejected`

### Booking flow

```text
Customer asks to book
   ↓
collect required details
   ↓
generate slot suggestions
   ↓
confirm draft booking
   ↓
generate booking ID
   ↓
store booking + summary
   ↓
set state = pending_advisor_approval
   ↓
Advisor approves or rejects
   ↓
if approved:
   - send confirmation email
   - create calendar hold
   - optionally append Sheets row
   - update state
```

### Cancellation flow

```text
Customer provides booking ID
   ↓
verify booking
   ↓
cancel booking
   ↓
store cancellation event
   ↓
return cancellation confirmation
```

### Booking ID rules

- human-readable
- unique
- easy to copy
- visible in customer and advisor views

**Example pattern:** `BK-20260425-0012`

---

## Weekly pulse architecture

### Purpose

Generate a PM-facing pulse summarizing review or issue trends, and optionally send it to subscribers weekly.

### Pulse generation flow

```text
Groww Play Store reviews (Playwright collection) and/or other issue inputs
   ↓
persist raw payloads (immutable or versioned) for audit/debug
   ↓
normalization layer (dedupe, language detection, spam/low-signal filtering, PII scrubbing, schema mapping)
   ↓
optional chunking / segmentation for long reviews (pulse preprocessing, not RAG retrieval)
   ↓
Groq preprocessing
   ↓
theme extraction
   ↓
quote selection candidate generation
   ↓
Gemini synthesis
   ↓
store weekly pulse
   ↓
render in Product tab
   ↓
optional scheduled email send
```

### Weekly send flow

```text
GitHub Actions cron (Monday 10 a.m. IST)
   ↓
POST /api/v1/internal/scheduler/pulse
   ↓
scheduler_service
   ↓
load active subscribers
   ↓
load latest pulse
   ↓
MCP send_weekly_pulse_email
   ↓
Gmail API via OAuth
   ↓
log send results
```

### Product analytics

The Product tab should also show booking issue analytics derived from:

- chat summaries
- booking summaries
- booking issue tags

Do not use Google Sheets as analytics source.

---

## Advisor approval architecture

### Advisor responsibilities

- review pending booking actions
- inspect summary context
- approve or reject
- review upcoming slots / confirmed items

### Approval flow

```text
booking created
   ↓
pending advisor approval
   ↓
advisor tab fetches pending records
   ↓
advisor reviews summary
   ↓
approve or reject
   ↓
if approve:
   send booking confirmation
   create calendar hold
   optionally append Google Sheet export row
   persist action logs
```

### Advisor export to Google Sheets

Google Sheets is optional operational visibility only.

If used, append a compact row with:

- booking_id
- session_id
- customer_issue_theme
- appointment_slot_ist
- booking_summary
- fee_context
- approval_status
- confirmation_email_status
- created_at
- updated_at

Do not store full chat history in Sheets.

---

## Badge architecture

Badges should be computed by the backend and rendered by the frontend.

### Badge endpoint

- `GET /api/v1/dashboard/badges`

### Customer badges

Examples:

- booking in progress
- follow-up available
- voice ready

### Product badges

Examples:

- pulse ready
- active subscribers count
- next scheduled send
- send failure warning

### Advisor badges

Examples:

- pending approvals count
- upcoming bookings today
- recently rejected items
- cancellations to review

### Rule

Frontend should never compute true business badge state on its own.

---

## Data architecture

### Source of truth

Supabase Postgres is the source of truth for all app state.

### Main tables

#### Core

- `app_users`
- `app_sessions`
- `audit_logs`

#### Google auth

- `google_oauth_tokens`

#### Pulse

- `review_uploads`
- `reviews_raw`
- `pulse_runs`
- `weekly_pulses`
- `pulse_subscriptions`
- `pulse_send_logs`

#### Chat

- `chat_sessions`
- `chat_messages`
- `chat_summaries`

#### RAG

- `source_documents`
- `document_chunks`
- `retrieval_logs`

#### Booking

- `bookings`
- `booking_slots`
- `booking_events`
- `booking_cancellations`

#### Advisor / approval

- `advisor_approvals`
- `calendar_events`
- `email_actions`
- `external_sync_logs`

#### Analytics

- `booking_issue_analytics`
- `tab_badge_state`

### Data rules

- store chat history in DB
- store booking state transitions in DB
- store approval actions in DB
- store pulse results in DB
- store send logs in DB
- store Google action outcomes in DB
- use Google Sheets only as export / visibility layer if needed

---

## API contract

All backend routes should be under:

- `/api/v1/...`

### Standard response envelope

```json
{
  "success": true,
  "message": "optional status message",
  "data": {},
  "errors": []
}
```

### Auth

- `GET /api/v1/auth/google/login`
- `GET /api/v1/auth/google/callback`
- `POST /api/v1/auth/google/refresh`
- `POST /api/v1/auth/google/disconnect`

### Health

- `GET /api/v1/health`

### Dashboard

- `GET /api/v1/dashboard/badges`

### Pulse

- `POST /api/v1/pulse/generate`
- `GET /api/v1/pulse/current`
- `GET /api/v1/pulse/history`
- `POST /api/v1/pulse/subscribe`
- `POST /api/v1/pulse/unsubscribe`
- `POST /api/v1/pulse/send-now`

### Chat

- `POST /api/v1/chat/message`
- `GET /api/v1/chat/history/{session_id}`
- `GET /api/v1/chat/prompts`

### Booking

- `POST /api/v1/booking/create`
- `POST /api/v1/booking/cancel`
- `GET /api/v1/booking/{booking_id}`

### Advisor

- `GET /api/v1/advisor/pending`
- `GET /api/v1/advisor/upcoming`

### Approval

- `POST /api/v1/approval/{approval_id}/approve`
- `POST /api/v1/approval/{approval_id}/reject`

### Voice

- `POST /api/v1/voice/transcribe`
- `POST /api/v1/voice/respond`

### Internal

- `POST /api/v1/internal/scheduler/pulse`
- `POST /api/v1/evals/run`

---

## Frontend architecture

### Frontend responsibilities

- render dashboard
- render 3 tabs
- fetch backend data
- submit forms and actions
- render loading and error states
- keep view state local
- keep business logic minimal

### Frontend component groups

- dashboard
- customer
- product
- advisor
- shared UI components

### Key UI components

**Dashboard:**

- DashboardShell
- RoleTabs
- ActionBadge
- StatusBanner

**Customer:**

- CustomerTab
- ChatPanel
- PromptChips
- VoiceControls
- BookingCard
- ChatHistory

**Product:**

- ProductTab
- PulseCard
- SubscribePanel
- IssueAnalytics
- SendStatusCard

**Advisor:**

- AdvisorTab
- PendingApprovalsTable
- BookingSummaryDrawer
- UpcomingSlots
- ApprovalActions

---

## Repo structure

```text
project-root/
├── frontend/
│   ├── app/
│   │   ├── page.tsx
│   │   ├── layout.tsx
│   │   ├── globals.css
│   │   └── api/                       # optional proxy helpers only
│   ├── components/
│   │   ├── dashboard/
│   │   ├── customer/
│   │   ├── product/
│   │   ├── advisor/
│   │   └── shared/
│   ├── lib/
│   │   ├── api-client.ts
│   │   ├── constants.ts
│   │   ├── badge-config.ts
│   │   └── formatters.ts
│   ├── public/
│   ├── package.json
│   └── tsconfig.json
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   ├── security.py
│   │   │   └── dependencies.py
│   │   ├── api/
│   │   │   ├── router.py
│   │   │   └── v1/
│   │   │       ├── auth.py
│   │   │       ├── health.py
│   │   │       ├── dashboard.py
│   │   │       ├── pulse.py
│   │   │       ├── chat.py
│   │   │       ├── booking.py
│   │   │       ├── advisor.py
│   │   │       ├── approval.py
│   │   │       ├── voice.py
│   │   │       ├── internal.py
│   │   │       └── evals.py
│   │   ├── schemas/
│   │   │   ├── common.py
│   │   │   ├── auth.py
│   │   │   ├── pulse.py
│   │   │   ├── chat.py
│   │   │   ├── booking.py
│   │   │   ├── advisor.py
│   │   │   └── approval.py
│   │   ├── models/
│   │   │   ├── auth.py
│   │   │   ├── pulse.py
│   │   │   ├── chat.py
│   │   │   ├── booking.py
│   │   │   ├── approval.py
│   │   │   └── logs.py
│   │   ├── repositories/
│   │   │   ├── token_repository.py
│   │   │   ├── pulse_repository.py
│   │   │   ├── chat_repository.py
│   │   │   ├── booking_repository.py
│   │   │   ├── approval_repository.py
│   │   │   ├── analytics_repository.py
│   │   │   ├── subscription_repository.py
│   │   │   └── log_repository.py
│   │   ├── services/
│   │   │   ├── google_oauth_service.py
│   │   │   ├── customer_router_service.py
│   │   │   ├── pulse_workflow_service.py
│   │   │   ├── booking_workflow_service.py
│   │   │   ├── approval_workflow_service.py
│   │   │   ├── badge_service.py
│   │   │   ├── scheduler_service.py
│   │   │   ├── advisor_context_service.py
│   │   │   └── prompt_service.py
│   │   ├── rag/
│   │   │   ├── ingest.py
│   │   │   ├── chunk.py
│   │   │   ├── bm25.py
│   │   │   ├── embeddings.py
│   │   │   ├── fusion.py
│   │   │   ├── rerank.py
│   │   │   ├── retrieve.py
│   │   │   └── answer.py
│   │   ├── llm/
│   │   │   ├── groq_client.py
│   │   │   ├── gemini_client.py
│   │   │   ├── task_router.py
│   │   │   ├── prompt_registry.py
│   │   │   └── cache.py
│   │   ├── integrations/
│   │   │   ├── supabase/
│   │   │   │   └── client.py
│   │   │   └── google/
│   │   │       ├── gmail_client.py
│   │   │       ├── calendar_client.py
│   │   │       ├── sheets_client.py
│   │   │       ├── stt_client.py
│   │   │       └── tts_client.py
│   │   ├── mcp/
│   │   │   ├── send_weekly_pulse_email.py
│   │   │   ├── send_booking_confirmation.py
│   │   │   ├── create_calendar_hold.py
│   │   │   ├── append_advisor_sheet_row.py
│   │   │   ├── get_latest_pulse_context.py
│   │   │   └── get_booking_summary.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   └── migrations/
│   │   └── evals/
│   │       ├── golden_dataset.py
│   │       ├── adversarial_checks.py
│   │       ├── pulse_checks.py
│   │       ├── booking_checks.py
│   │       └── run_all.py
│   ├── requirements.txt
│   └── render.yaml
│
├── shared/
│   ├── prompts/
│   ├── source_manifest/
│   │   └── source_manifest.csv
│   ├── fixtures/
│   └── api-contracts/
│
├── infra/
│   ├── architecture/
│   │   ├── architecture.md
│   │   ├── db-schema.md
│   │   ├── auth-matrix.md
│   │   ├── scheduler-spec.md
│   │   └── phase-plan.md
│   ├── vercel/
│   ├── render/
│   └── supabase/
│
├── scripts/
│   ├── seed_dev_data.py
│   ├── fetch_groww_playstore_reviews.py   # Playwright: Groww Play Store listing
│   ├── ingest_sources.py
│   ├── normalize_collected_text.py        # optional: shared normalization entrypoint
│   ├── rebuild_index.py
│   └── run_pulse.py
│
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── weekly-pulse.yml
│
├── .env.example
└── README.md
```

*Note: This repo also uses `Docs/` for project documentation; keep architecture docs in `Docs/Architecture.md` in addition to (or as the source for) any copy under `infra/architecture/`.

---

## Environment variables

### Frontend

```env
NEXT_PUBLIC_API_BASE_URL=
```

Only add frontend Supabase vars if the frontend directly uses Supabase.

Otherwise, frontend talks only to FastAPI.

### Backend

```env
APP_ENV=
LOG_LEVEL=

API_BASE_URL=
FRONTEND_BASE_URL=

SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

GEMINI_API_KEY=
GEMINI_API_KEY_FALLBACK=
GEMINI_MODEL=gemini-2.5-flash
GROQ_API_KEY=
GROQ_API_KEY_FALLBACK=

GOOGLE_PROJECT_ID=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=
GOOGLE_OAUTH_SCOPES=

GOOGLE_AUTHORIZED_EMAIL=
GMAIL_SENDER_EMAIL=
GOOGLE_CALENDAR_ID=
GOOGLE_SHEETS_SPREADSHEET_ID=
GOOGLE_SHEETS_WORKSHEET_NAME=

TOKEN_ENCRYPTION_KEY=
SCHEDULER_SHARED_SECRET=

DEFAULT_TIMEZONE=Asia/Kolkata
```

### Env rules

- `GEMINI_MODEL` defaults to **`gemini-2.5-flash`**; change only with explicit compatibility testing.
- `GEMINI_API_KEY_FALLBACK` and `GROQ_API_KEY_FALLBACK` are backend-only; the runtime **must** use them when primary keys hit quota or token limits as described in **API keys, quotas, and fallbacks** under LLM task split.
- `SUPABASE_SERVICE_ROLE_KEY` is backend-only
- `GOOGLE_CLIENT_SECRET` is backend-only
- refresh tokens are backend-only
- never expose Google or Supabase elevated secrets to frontend
- `API_BASE_URL` and `FRONTEND_BASE_URL` are typically different origins (for example, `localhost:8000` and `localhost:3000`), so backend CORS configuration is mandatory to avoid browser SOP/CORS failures
- if credentials/cookies are used, do not use wildcard CORS origins; allow explicit frontend origins only

---

## Phase plan

### Mandatory phase quality gate (applies to every phase)

After each phase (Phase 1 through Phase 8), the team must complete this gate **before** starting the next phase:

1. Run implementation tests for the completed phase.
2. Fix any runtime, integration, or validation errors found.
3. Run phase-specific evals for the completed phase.
4. Record the phase score.
5. If the score is **below 85%**, make changes and re-run tests/evals until score is **at least 85%**.
6. Only then proceed to the next phase.

**Artifact requirement:** every phase must produce an eval artifact under:

- `Deliverables/Evals/`

Use one subfolder per phase (recommended):

- `Deliverables/Evals/phase-1/`
- `Deliverables/Evals/phase-2/`
- `Deliverables/Evals/phase-3/`
- `Deliverables/Evals/phase-4/`
- `Deliverables/Evals/phase-5/`
- `Deliverables/Evals/phase-6/`
- `Deliverables/Evals/phase-7/`
- `Deliverables/Evals/phase-8/`

### Phase 1

- Refer to the UI.md, Failures&EdgeCases.md, Rules.md, Runbook.md
- frontend dashboard shell
- FastAPI skeleton
- health route
- badges route
- Supabase connection foundation
- local cross-origin setup (frontend `localhost:3000` to backend `localhost:8000`) with explicit FastAPI CORS allowlist
- validate preflight (`OPTIONS`) and standard API calls from frontend to backend without SOP/CORS errors

### Phase 2

- Refer to UI.md, Failures&EdgeCases.md, Rules.md, Runbook.md
- Weekly Pulse backend
- pulse APIs
- Product tab UI
- subscribe / unsubscribe
- **Groww Play Store** review collection job using **Playwright**; persist raw → **normalization** → optional **chunking/segmentation** for pulse input; store in `reviews_raw` (or equivalent) before Groq/Gemini pulse pipeline

### Phase 3

- Refer to UI.md, Failures&EdgeCases.md, Rules.md, Runbook.md
- text chat
- prompt chips
- chat persistence
- customer routing skeleton

### Phase 4

- Refer to the UI.md, Failures&EdgeCases.md, Rules.md, Runbook.md
- Refer to Failures&EdgeCases.md, Rules.md, Runbook.md
- RAG engine
- grounded MF Q&A
- fee explanation Q&A
- hybrid Q&A
- **Scraped / imported MF and fee sources:** raw persist → **normalization layer** → **chunking** → BM25 + embedding indexes; wire `ingest_sources.py` / `rebuild_index.py` into documented runbook steps

### Phase 5

- Refer to Failures&EdgeCases.md, Rules.md, Runbook.md
- booking and cancellation workflow
- booking ID generation
- booking persistence

### Phase 6

- Refer to the UI.md, Failures&EdgeCases.md, Rules.md, Runbook.md
- advisor approval flow
- advisor tab
- optional Google Sheets export via OAuth

### Phase 7

- Refer to Failures&EdgeCases.md, Rules.md, Runbook.md
- Gmail send via OAuth
- Calendar event creation via OAuth
- MCP governed actions
- scheduler webhook
- weekly pulse send automation
- production CORS/domain hardening (`FRONTEND_BASE_URL` and deployed API origin must be explicitly allowlisted)
- ensure OAuth callback domain and frontend/backend URLs are consistent with deployed origins

### Phase 8

- Refer to Failures&EdgeCases.md, Rules.md, Runbook.md
- voice STT/TTS
- evals
- hardening

---

## Cursor implementation rules

- implement one phase at a time
- after each phase, run tests, fix errors and run evals before phase transition
- fix all discovered errors before phase transition
- enforce minimum eval score of 85% before moving to next phase
- store per-phase eval outputs under `Deliverables/Evals/phase-*`
- do not create a different repo structure per phase
- do not split into separate repos
- do not move business logic into frontend
- keep Google API usage backend-only
- keep OAuth token management centralized
- keep MCP thin
- keep Supabase as source of truth
- keep Sheets optional and downstream
- prefer small, testable services
- avoid broad refactors unless explicitly requested

---

## Non-goals

- multi-tenant user authentication
- complex RBAC
- distributed microservices
- event bus architecture
- service-account-based Google automation
- Sheets as database
- heavy MCP-first orchestration
- fully autonomous agent behavior

---

## Definition of done

The project is considered complete when:

- Customer tab supports text chat, hybrid Q&A, booking, and cancellation
- Product tab shows current Weekly Pulse, subscription state, and issue analytics
- Advisor tab shows pending approvals and approval actions
- booking approval triggers Gmail + Calendar governed actions through OAuth-backed backend integrations
- badge counts update correctly across tabs
- all core state is persisted in Supabase
- Google Sheets, if used, is only a downstream export
- the app is deployable on Vercel + Render
- architecture remains modular and debuggable
