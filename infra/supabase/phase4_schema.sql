-- Phase 4 additive migration: RAG knowledge base tables.
-- Apply after phase1_phase2_schema.sql (all DDL is additive; Rules D4).
-- Source of truth: Docs/Architecture.md + Docs/Low Level Architecture.md §10.2.

-- =========================
-- Phase 4 RAG tables
-- =========================

-- Scraped / ingested source documents (MF pages + fee explainer corpus).
create table if not exists public.source_documents (
  doc_id text primary key,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  url text not null unique,
  title text not null,
  doc_type text not null check (doc_type in ('mutual_fund_page', 'fee_explainer')),
  last_checked date not null,
  content_hash text not null,
  raw_char_count int not null default 0,
  status text not null default 'active' check (status in ('active', 'stale', 'error'))
);

create index if not exists source_documents_doc_type_idx on public.source_documents(doc_type);
create index if not exists source_documents_updated_at_idx on public.source_documents(updated_at desc);

-- Chunked segments derived from source documents.
-- Embeddings are stored as a JSONB float array; vector search is done in-memory
-- for Phase 4 (pgvector can be added in a later additive migration).
create table if not exists public.document_chunks (
  chunk_id text primary key,
  doc_id text not null references public.source_documents(doc_id) on delete cascade,
  source_url text not null,
  title text not null,
  doc_type text not null,
  last_checked date not null,
  content text not null,
  chunk_index int not null default 0,
  embedding jsonb null,   -- list[float] stored as JSON array; null if not yet embedded
  created_at timestamptz not null default now()
);

create index if not exists document_chunks_doc_id_idx on public.document_chunks(doc_id);
create index if not exists document_chunks_created_at_idx on public.document_chunks(created_at desc);

-- Retrieval audit log: records every hybrid retrieval call for debuggability (Rules O1, O2).
create table if not exists public.retrieval_logs (
  log_id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  session_id text null,
  correlation_id text null,
  query text not null,
  intent text not null,
  chunks_retrieved int not null default 0,
  top_chunk_ids jsonb not null default '[]'::jsonb,
  fallback boolean not null default false,
  fallback_reason text null,
  duration_ms int null
);

create index if not exists retrieval_logs_session_id_idx on public.retrieval_logs(session_id);
create index if not exists retrieval_logs_created_at_idx on public.retrieval_logs(created_at desc);

-- =========================
-- Phase 4 extended: structured MF fund metrics table
-- Additive migration — no existing tables modified.
-- =========================

-- Structured mutual-fund metrics extracted from Groww MF pages.
-- Fields unavailable from static HTML (nav, aum_cr, returns, holdings, etc.)
-- are nullable and may be populated by approved HTTP-only enrichment sources.
create table if not exists public.mf_fund_metrics (
  doc_id text primary key references public.source_documents(doc_id) on delete cascade,
  fund_name text not null,
  amc text,
  category text,
  sub_category text,
  plan text,
  option text,
  nav numeric(12,4),
  nav_date date,
  aum_cr numeric(16,2),
  expense_ratio_pct numeric(6,4),
  exit_load_pct numeric(6,4),
  exit_load_window_days int,
  exit_load_description text,
  risk_level text,
  rating text,
  benchmark text,
  min_sip_amount numeric(12,2),
  min_lumpsum_amount numeric(12,2),
  returns jsonb,           -- MFReturns serialised as JSON object
  investment_returns jsonb, -- list[MFInvestmentReturn] serialised as JSON array
  returns_and_rankings jsonb, -- MFReturnsAndRankings serialised as JSON object
  top_holdings jsonb,      -- list[MFHolding] serialised as JSON array
  advanced_ratios jsonb,   -- dict[str, float] serialised as JSON object
  fund_managers jsonb,     -- list[MFFundManager] serialised as JSON array
  sector_allocation jsonb, -- list[MFSectorAlloc] serialised as JSON array
  asset_allocation jsonb,  -- dict[str, float] serialised as JSON object
  fund_objective text,
  scraped_at timestamptz not null,
  last_checked date not null,
  updated_at timestamptz not null default now()
);

create index if not exists mf_fund_metrics_amc_idx on public.mf_fund_metrics(amc);
create index if not exists mf_fund_metrics_category_idx on public.mf_fund_metrics(category);
create index if not exists mf_fund_metrics_updated_at_idx on public.mf_fund_metrics(updated_at desc);
