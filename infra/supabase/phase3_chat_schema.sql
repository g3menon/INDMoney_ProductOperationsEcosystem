-- Phase 3 additive migration: chat persistence tables
-- Apply in Supabase SQL editor AFTER phase1_phase2_schema.sql
-- Source of truth: Docs/Low Level Architecture.md §10.2

create table if not exists public.chat_sessions (
  id          text        primary key,                          -- CS-{12hex} prefix
  created_at  timestamptz not null default now()
);

create index if not exists chat_sessions_created_at_idx
  on public.chat_sessions(created_at desc);

create table if not exists public.chat_messages (
  id          text        primary key,                          -- MSG-{12hex} prefix
  session_id  text        not null references public.chat_sessions(id) on delete cascade,
  role        text        not null check (role in ('user', 'assistant')),
  content     text        not null,
  created_at  timestamptz not null default now()
);

create index if not exists chat_messages_session_id_idx
  on public.chat_messages(session_id);
create index if not exists chat_messages_created_at_idx
  on public.chat_messages(created_at asc);
