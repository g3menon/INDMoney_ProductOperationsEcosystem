-- Phase 2: Weekly Pulse tables (minimal subset).
-- Apply in Supabase SQL editor. All writes are additive (D4).

create table if not exists public.reviews_raw (
  id bigserial primary key,
  source text not null default 'playstore',
  review_id text not null,
  rating int not null,
  text text not null,
  review_date date null,
  found_review_helpful int null,
  device text not null default 'Unknown',
  collected_at timestamptz not null default now()
);

create index if not exists reviews_raw_review_id_idx on public.reviews_raw(review_id);
create index if not exists reviews_raw_collected_at_idx on public.reviews_raw(collected_at desc);

create table if not exists public.reviews_normalized (
  review_id text primary key,
  rating int not null,
  text text not null,
  review_date date null,
  found_review_helpful int null,
  device text not null default 'Unknown',
  content_hash text not null,
  normalized_at timestamptz not null default now()
);

create index if not exists reviews_normalized_normalized_at_idx on public.reviews_normalized(normalized_at desc);

create table if not exists public.weekly_pulses (
  pulse_id text primary key,
  created_at timestamptz not null default now(),
  metrics jsonb not null,
  themes jsonb not null,
  quotes jsonb not null,
  recommended_actions jsonb not null,
  narrative text not null,
  degraded boolean not null default false,
  degraded_reason text null
);

create index if not exists weekly_pulses_created_at_idx on public.weekly_pulses(created_at desc);

create table if not exists public.pulse_subscriptions (
  email text primary key,
  active boolean not null default true,
  updated_at timestamptz not null default now()
);

create index if not exists pulse_subscriptions_active_idx on public.pulse_subscriptions(active);
