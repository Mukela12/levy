-- ════════════════════════════════════════════════════════════════════════
-- MATTER WORKSPACE: a persistent case container.
--
-- A "matter" is one legal case a user (a self-representing litigant or a
-- lawyer) runs across many chat sessions: it holds the parties, court, cause
-- number, a running facts summary and key dates, and links the chat threads
-- and drafts that belong to that case. When a chat session is attached to a
-- matter, the agent is given the matter's context so Levy "remembers" the case
-- across sessions and puts the right details into every draft.
--
-- Security model matches the rest of the app: the frontend reads/writes these
-- rows directly with the anon key, so RLS locks every row to its owner via
-- auth.uid(); the backend uses the service_role key (BYPASSRLS) for the agent's
-- context injection and the update_matter tool.
-- ════════════════════════════════════════════════════════════════════════

create table if not exists matters (
  id            uuid primary key default gen_random_uuid(),
  owner_id      uuid not null,
  title         text not null,
  matter_type   text,                         -- e.g. 'Unfair dismissal', 'Caveat removal'
  court         text,                          -- court / division, e.g. 'Industrial Relations Division'
  cause_number  text,                          -- e.g. '2026/HP/1234'
  parties       jsonb default '[]'::jsonb,     -- [{"role":"Applicant","name":"..."}, ...]
  facts         text,                          -- running case narrative the agent + user build up
  key_dates     jsonb default '[]'::jsonb,     -- [{"label":"Hearing","date":"2026-08-06","note":"..."}]
  status        text default 'active',         -- 'active' | 'closed'
  created_at    timestamptz default now(),
  updated_at    timestamptz default now()
);

create index if not exists matters_owner_idx on matters (owner_id, updated_at desc);

-- Link chat sessions and artifacts to a matter (nullable; a thread/draft can
-- exist without one). ON DELETE SET NULL so deleting a matter never destroys
-- the underlying conversations or documents.
alter table chat_sessions add column if not exists matter_id uuid references matters(id) on delete set null;
alter table artifacts     add column if not exists matter_id uuid references matters(id) on delete set null;

create index if not exists chat_sessions_matter_idx on chat_sessions (matter_id);
create index if not exists artifacts_matter_idx on artifacts (matter_id);

-- ── RLS: owner only (same pattern as chat_sessions / document_folders) ──────
alter table matters enable row level security;
drop policy if exists matters_owner on matters;
create policy matters_owner on matters
  for all to authenticated
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid());
