-- Lookups of ZambiaLII's judgment index through Laws.Africa's API
-- (backend/app/services/case_index.py). One row per call that reached the
-- service. It is the cache (the same case is never paid for twice within 30
-- days) and the usage log (how many calls a day, how many failed, how slow).
-- The backend works without this table: it then caches in memory only.
create table if not exists public.case_index_lookups (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  purpose text not null,              -- 'verify' or 'search'
  query text not null,                -- normalised query text
  status text not null,               -- 'ok', 'timeout', 'http_503', 'throttled', ...
  latency_ms integer,
  hits integer,
  day_remaining integer,              -- calls left that UTC day, as the service reported
  results jsonb                       -- cleaned results, only when status = 'ok'
);
create index if not exists case_index_lookups_query_idx
  on public.case_index_lookups (query, created_at desc);
create index if not exists case_index_lookups_created_idx
  on public.case_index_lookups (created_at desc);
-- Service role only: no policies, so the anon and authenticated roles see nothing.
alter table public.case_index_lookups enable row level security;
