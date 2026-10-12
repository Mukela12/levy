-- 12 Oct 2026. Run once in the Supabase SQL editor; safe to re-run.

-- 1. Why a visitor failed the browser check: coarse browser class, whether a
--    token was sent, Cloudflare's error codes, the widget's own error code
--    (routes/api.py _log_anon). The backend writes rows without it until
--    this column exists.
alter table public.anon_events add column if not exists meta jsonb;

-- 2. Levy's shared memory of recent official legal facts the library does not
--    yet hold (services/legal_updates.py). No user or chat data: each row is
--    a public fact, the official URL it came from, and a passage the server
--    found on that page itself.
create table if not exists public.legal_updates (
  id uuid primary key default gen_random_uuid(),
  topic text not null,
  kind text not null check (kind in ('commencement', 'new_law', 'amendment', 'repeal', 'rate_change', 'court_rule', 'other')),
  statement text not null check (char_length(statement) <= 600),
  statement_hash text not null,
  effective_date date,
  act_title text,
  document_id uuid,
  value jsonb,
  source_url text not null,
  source_domain text not null,
  source_quote text not null check (char_length(source_quote) <= 1200),
  source_hash text,
  status text not null default 'pending' check (status in ('pending', 'verified', 'approved', 'rejected', 'superseded')),
  origin text not null default 'chat' check (origin in ('chat', 'watcher', 'admin')),
  seen_count integer not null default 1,
  first_seen_at timestamptz not null default now(),
  last_checked_at timestamptz,
  verified_at timestamptz,
  reviewed_at timestamptz,
  review_note text
);
create unique index if not exists legal_updates_dedupe on public.legal_updates (topic, statement_hash);
create index if not exists legal_updates_status on public.legal_updates (status, first_seen_at desc);
alter table public.legal_updates enable row level security;
-- No policies on purpose: only the backend's service key reads or writes it.

-- 3. What the official-source watcher last saw on each page it checks.
create table if not exists public.watch_snapshots (
  url text primary key,
  content_hash text not null,
  excerpt text,
  checked_at timestamptz not null default now(),
  changed_at timestamptz
);
alter table public.watch_snapshots enable row level security;
