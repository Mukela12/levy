-- 27 Oct 2026. Levy News, shadow mode. Run once in the Supabase SQL editor; safe to re-run.
--
-- The daily pipeline (backend/app/services/news) collects Zambian headlines,
-- groups them into stories, checks the most check-worthy claims and stores each
-- check for the editor to review. Nothing here is shown to users yet, and only
-- the backend's service key reads or writes these tables.

-- 1. Every headline the feeds have offered, once per URL.
create table if not exists public.news_items (
  id uuid primary key default gen_random_uuid(),
  url text not null,
  url_hash text not null unique,
  outlet text not null,
  outlet_type text not null check (outlet_type in ('state', 'private', 'social', 'official', 'aggregator', 'fact_checker')),
  title text not null,
  summary text,
  published_at timestamptz,
  fetched_at timestamptz not null default now(),
  feed text
);
create index if not exists news_items_published on public.news_items (published_at desc);

-- 2. A story is the same event across outlets, with the claim worth checking.
create table if not exists public.news_stories (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  claim text,
  category text,
  risk jsonb not null default '{}'::jsonb,
  check_worthy smallint not null default 0,
  item_count integer not null default 0,
  outlet_count integer not null default 0,
  social_count integer not null default 0,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  status text not null default 'new' check (status in ('new', 'checked', 'skipped', 'failed')),
  created_at timestamptz not null default now()
);
create index if not exists news_stories_recent on public.news_stories (last_seen_at desc);

create table if not exists public.news_story_items (
  story_id uuid not null references public.news_stories (id) on delete cascade,
  item_id uuid not null references public.news_items (id) on delete cascade,
  primary key (story_id, item_id)
);

-- 3. A check: the verdict, the reader-facing text, the evidence with whether
--    each quote was found on its page, and the editor's review. Versions keep
--    every earlier verdict when a story is checked again.
create table if not exists public.news_checks (
  id uuid primary key default gen_random_uuid(),
  story_id uuid not null references public.news_stories (id) on delete cascade,
  version integer not null default 1,
  label text not null check (label in ('True', 'Misleading', 'False', 'Unproven')),
  confidence smallint,
  headline text,
  claim text not null,
  verdict_text text,
  what_we_found text,
  case_for jsonb not null default '[]'::jsonb,
  case_against jsonb not null default '[]'::jsonb,
  would_change text,
  evidence jsonb not null default '[]'::jsonb,
  evidence_summary text,
  flags jsonb not null default '[]'::jsonb,
  review_status text not null default 'pending' check (review_status in ('pending', 'approved', 'rejected', 'held')),
  review_note text,
  reviewed_at timestamptz,
  recheck_at timestamptz,
  models jsonb,
  cost_usd numeric(8, 4),
  created_at timestamptz not null default now()
);
create unique index if not exists news_checks_version on public.news_checks (story_id, version);
create index if not exists news_checks_review on public.news_checks (review_status, created_at desc);

-- 4. One row per run: what came in, what was checked, what it cost.
create table if not exists public.news_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  items_new integer not null default 0,
  stories_new integer not null default 0,
  checks_made integer not null default 0,
  cost_usd numeric(8, 4) not null default 0,
  note text
);
create index if not exists news_runs_started on public.news_runs (started_at desc);

alter table public.news_items enable row level security;
alter table public.news_stories enable row level security;
alter table public.news_story_items enable row level security;
alter table public.news_checks enable row level security;
alter table public.news_runs enable row level security;
-- No policies on purpose: only the backend's service key reads or writes them.
