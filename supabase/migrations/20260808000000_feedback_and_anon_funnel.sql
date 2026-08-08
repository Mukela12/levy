-- ════════════════════════════════════════════════════════════════════════
-- 1. ANSWER FEEDBACK  — the missing quality signal
-- 2. ANONYMOUS FUNNEL — the missing conversion signal
--
-- Three field-study reports have been produced by reading every conversation
-- by hand, because nothing in Levy records whether an answer was any good.
-- And since the Turnstile free trial shipped, anonymous runs have never been
-- persisted at all (api.py only writes when `safe_session_id and uid`), so the
-- biggest change we have made to the funnel is the one we cannot measure.
-- ════════════════════════════════════════════════════════════════════════

-- ── 1. Answer feedback ──────────────────────────────────────────────────
-- One vote per user per assistant message. `reason` is optional free text the
-- user types after a thumbs-down; it is the part that tells us WHY, and it is
-- worth far more than the count.
create table if not exists message_feedback (
  id          uuid primary key default gen_random_uuid(),
  message_id  uuid not null references chat_messages(id) on delete cascade,
  session_id  uuid references chat_sessions(id) on delete cascade,
  user_id     uuid not null,
  rating      text not null check (rating in ('up', 'down')),
  reason      text,
  created_at  timestamptz default now(),
  unique (message_id, user_id)
);

create index if not exists message_feedback_created_idx on message_feedback (created_at desc);
create index if not exists message_feedback_rating_idx  on message_feedback (rating, created_at desc);

-- RLS: a user may only see and write their own votes. The service role
-- (BYPASSRLS) reads across all of them for reporting.
alter table message_feedback enable row level security;
drop policy if exists message_feedback_owner on message_feedback;
create policy message_feedback_owner on message_feedback
  for all to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());


-- ── 2. Anonymous funnel ─────────────────────────────────────────────────
-- Deliberately content-free. We record THAT an anonymous attempt happened and
-- how it ended, never what was asked. There is no IP column: `visitor_hash` is
-- a salted, day-scoped digest computed in the backend, so two questions from
-- one visitor group together within a day and cannot be linked across days or
-- back to a person.
--
-- This exists to answer one question we currently cannot: when signed-in
-- questions fell, did demand actually drop, or did people just use the free
-- trial instead of registering?
create table if not exists anon_events (
  id            bigserial primary key,
  created_at    timestamptz default now(),
  outcome       text not null check (outcome in (
                  'asked',            -- passed every gate, question ran
                  'answered',         -- run completed and produced an answer
                  'failed',           -- run started but errored out
                  'bot_blocked',      -- bot user-agent
                  'no_turnstile_key', -- server not configured; failed closed
                  'rate_limited',     -- per-IP burst window
                  'turnstile_failed', -- challenge not solved
                  'trial_exhausted'   -- daily free allowance used up
                )),
  trial_number  smallint,   -- which of the day's free questions this was (1..N)
  visitor_hash  text,       -- salted day-scoped digest; NOT reversible to an IP
  duration_ms   integer,    -- populated on 'answered' / 'failed'
  had_sources   boolean     -- did the answer cite the corpus?
);

create index if not exists anon_events_created_idx on anon_events (created_at desc);
create index if not exists anon_events_outcome_idx on anon_events (outcome, created_at desc);
create index if not exists anon_events_visitor_idx on anon_events (visitor_hash, created_at desc);

-- Written only by the backend service role. No anon/authenticated policy is
-- created, so with RLS on, the public anon key can neither read nor write it.
alter table anon_events enable row level security;
