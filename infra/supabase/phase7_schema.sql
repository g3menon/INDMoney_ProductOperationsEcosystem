-- Phase 7: External integrations + scheduler (Gmail, Calendar, Sheets, OAuth tokens)
-- Additive migration — does not modify any existing table (Rules D4).
-- Apply after: phase1_phase2_schema.sql, phase3_chat_schema.sql, phase4_schema.sql, phase5_schema.sql.
--
-- Source of truth:
-- - Docs/Low Level Architecture.md §14.7 + §10.2
-- - Docs/Rules.md (Phase 7, D7)
--
-- Notes:
-- - OAuth tokens are stored encrypted at rest (ciphertext strings produced by Fernet).
-- - This migration intentionally does NOT create RLS policies; service-role access is assumed for backend writes.

create extension if not exists pgcrypto;

-- ─────────────────────────────────────────────────────────────────────────────
-- google_oauth_tokens
-- Stores encrypted tokens for the operational Google account.
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists public.google_oauth_tokens (
  authorized_email            text primary key,
  scopes                      text not null default '',
  encrypted_refresh_token     text not null,
  encrypted_access_token      text null,
  access_token_expires_at     timestamptz null,
  created_at                  timestamptz not null default now(),
  updated_at                  timestamptz not null default now()
);

create index if not exists google_oauth_tokens_updated_at_idx
  on public.google_oauth_tokens(updated_at desc);

-- ─────────────────────────────────────────────────────────────────────────────
-- email_actions
-- Tracks idempotent email send attempts (booking confirmations and weekly pulse).
-- Provider fields are intentionally generic (Gmail now; others later).
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists public.email_actions (
  action_id               uuid primary key default gen_random_uuid(),
  created_at              timestamptz not null default now(),
  correlation_id          text null,
  idempotency_key         text null,
  action_type             text not null check (action_type in ('booking_confirmation', 'weekly_pulse')),
  booking_id              text null,
  pulse_id                text null references public.weekly_pulses(pulse_id) on delete set null,
  to_email                text not null,
  from_email              text null,
  subject                 text not null,
  status                  text not null check (status in ('queued', 'sent', 'skipped', 'failed')),
  provider_message_id     text null,
  error                   text null
);

create unique index if not exists email_actions_idempotency_key_uq
  on public.email_actions(idempotency_key)
  where idempotency_key is not null;

create index if not exists email_actions_created_at_idx
  on public.email_actions(created_at desc);

create index if not exists email_actions_booking_id_idx
  on public.email_actions(booking_id);

create index if not exists email_actions_pulse_id_idx
  on public.email_actions(pulse_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- calendar_events
-- Tracks Calendar event create attempts.
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists public.calendar_events (
  event_row_id           uuid primary key default gen_random_uuid(),
  created_at             timestamptz not null default now(),
  correlation_id         text null,
  booking_id             text not null,
  status                 text not null check (status in ('created', 'skipped', 'conflict', 'failed')),
  provider_event_id      text null,
  error                  text null,
  conflict_payload       jsonb not null default '{}'::jsonb
);

create index if not exists calendar_events_created_at_idx
  on public.calendar_events(created_at desc);

create index if not exists calendar_events_booking_id_idx
  on public.calendar_events(booking_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- external_sync_logs
-- Generic log for governed external actions (Sheets append, Calendar, Gmail, scheduler runs).
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists public.external_sync_logs (
  log_id                 uuid primary key default gen_random_uuid(),
  created_at             timestamptz not null default now(),
  correlation_id         text null,
  entity_type            text not null,
  entity_id              text null,
  provider               text not null,
  action                 text not null,
  status                 text not null,
  detail                 jsonb not null default '{}'::jsonb
);

create index if not exists external_sync_logs_created_at_idx
  on public.external_sync_logs(created_at desc);

create index if not exists external_sync_logs_entity_idx
  on public.external_sync_logs(entity_type, entity_id);

