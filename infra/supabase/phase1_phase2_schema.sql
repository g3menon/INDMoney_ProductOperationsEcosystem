-- Supabase schema for Phase 1 + Phase 2 (minimum viable, additive).
-- Apply this in Supabase SQL editor for local/dev/staging.
-- Source of truth: Docs/Architecture.md (Data architecture, Weekly Pulse tables).

-- Enable extensions (safe if already enabled)
create extension if not exists pgcrypto;

-- =========================
-- Phase 1 core tables
-- =========================

create table if not exists public.app_users (
  user_id uuid primary key default gen_random_uuid(),
  email text unique,
  created_at timestamptz not null default now()
);

create table if not exists public.app_sessions (
  session_id uuid primary key default gen_random_uuid(),
  user_id uuid null references public.app_users(user_id) on delete set null,
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists app_sessions_last_seen_at_idx on public.app_sessions(last_seen_at desc);

create table if not exists public.audit_logs (
  audit_id bigserial primary key,
  created_at timestamptz not null default now(),
  correlation_id text null,
  actor text null,
  event_type text not null,
  entity_type text null,
  entity_id text null,
  detail jsonb not null default '{}'::jsonb
);

create index if not exists audit_logs_created_at_idx on public.audit_logs(created_at desc);
create index if not exists audit_logs_event_type_idx on public.audit_logs(event_type);

-- =========================
-- Phase 2 pulse ingestion + runs
-- =========================

create table if not exists public.review_uploads (
  upload_id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  source text not null default 'playstore',
  file_name text null,
  notes text null,
  raw_count int not null default 0,
  normalized_count int not null default 0,
  status text not null default 'created'
);

create index if not exists review_uploads_created_at_idx on public.review_uploads(created_at desc);

create table if not exists public.reviews_raw (
  id bigserial primary key,
  upload_id uuid null references public.review_uploads(upload_id) on delete set null,
  source text not null default 'playstore',
  review_id text not null,
  rating int not null check (rating between 1 and 5),
  text text not null,
  review_date date null,
  found_review_helpful int null check (found_review_helpful is null or found_review_helpful >= 0),
  device text not null default 'Unknown',
  collected_at timestamptz not null default now()
);

create index if not exists reviews_raw_review_id_idx on public.reviews_raw(review_id);
create index if not exists reviews_raw_collected_at_idx on public.reviews_raw(collected_at desc);
create index if not exists reviews_raw_upload_id_idx on public.reviews_raw(upload_id);

-- Normalized reviews used for pulse/theme LLM steps (no PII).
create table if not exists public.reviews_normalized (
  review_id text primary key,
  upload_id uuid null references public.review_uploads(upload_id) on delete set null,
  rating int not null check (rating between 1 and 5),
  text text not null,
  review_date date null,
  found_review_helpful int null check (found_review_helpful is null or found_review_helpful >= 0),
  device text not null default 'Unknown',
  content_hash text not null,
  normalized_at timestamptz not null default now()
);

create index if not exists reviews_normalized_normalized_at_idx on public.reviews_normalized(normalized_at desc);
create index if not exists reviews_normalized_hash_idx on public.reviews_normalized(content_hash);
create index if not exists reviews_normalized_upload_id_idx on public.reviews_normalized(upload_id);

create table if not exists public.pulse_runs (
  run_id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  upload_id uuid null references public.review_uploads(upload_id) on delete set null,
  lookback_weeks int not null default 8 check (lookback_weeks between 1 and 8),
  status text not null default 'created',
  degraded boolean not null default false,
  degraded_reason text null,
  metrics jsonb not null default '{}'::jsonb
);

create index if not exists pulse_runs_created_at_idx on public.pulse_runs(created_at desc);

create table if not exists public.weekly_pulses (
  pulse_id text primary key,
  created_at timestamptz not null default now(),
  run_id uuid null references public.pulse_runs(run_id) on delete set null,
  metrics jsonb not null,
  themes jsonb not null,
  quotes jsonb not null,
  recommended_actions jsonb not null,
  narrative text not null,
  degraded boolean not null default false,
  degraded_reason text null
);

create index if not exists weekly_pulses_created_at_idx on public.weekly_pulses(created_at desc);
create index if not exists weekly_pulses_run_id_idx on public.weekly_pulses(run_id);

create table if not exists public.pulse_subscriptions (
  email text primary key,
  active boolean not null default true,
  updated_at timestamptz not null default now()
);

create index if not exists pulse_subscriptions_active_idx on public.pulse_subscriptions(active);

create table if not exists public.pulse_send_logs (
  send_id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  pulse_id text null references public.weekly_pulses(pulse_id) on delete set null,
  email text not null,
  status text not null,
  provider_message_id text null,
  error text null
);

create index if not exists pulse_send_logs_created_at_idx on public.pulse_send_logs(created_at desc);
create index if not exists pulse_send_logs_pulse_id_idx on public.pulse_send_logs(pulse_id);
