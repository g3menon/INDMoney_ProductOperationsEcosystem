-- Phase 3 vector RAG storage.
-- Stores durable RAG chunks in Supabase with pgvector dense retrieval and
-- Postgres full-text search fallback.

create extension if not exists vector;

create table if not exists public.rag_chunks (
  id                   text primary key,
  doc_id               text,
  content              text not null,
  embedding            vector(768),
  doc_type             text,
  source_url           text,
  title                text,
  last_checked         timestamptz,
  chunk_index          integer default 0,
  created_at           timestamptz default now(),
  -- Play Store review metadata
  rating               smallint,
  review_date          timestamptz,
  app_version          text,
  found_review_helpful integer
);

create index if not exists rag_chunks_embedding_idx
  on public.rag_chunks
  using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);

create index if not exists rag_chunks_fts_idx
  on public.rag_chunks
  using gin (to_tsvector('english', content));

create index if not exists rag_chunks_doc_type_idx
  on public.rag_chunks (doc_type);

create index if not exists rag_chunks_source_url_idx
  on public.rag_chunks (source_url);

create or replace function match_chunks(
  query_embedding vector(768),
  match_count int
)
returns table (id text, content text, similarity float)
language sql stable
as $$
  select id, content,
    1 - (embedding <=> query_embedding) as similarity
  from public.rag_chunks
  where embedding is not null
  order by embedding <=> query_embedding
  limit match_count;
$$;

create or replace function get_rag_stats()
returns table (total_chunks int, chunks_with_embedding int, chunks_with_review_metadata int)
language sql stable
as $$
  select
    count(*)::int as total_chunks,
    count(*) filter (where embedding is not null)::int as chunks_with_embedding,
    count(*) filter (where rating is not null)::int as chunks_with_review_metadata
  from public.rag_chunks;
$$;
