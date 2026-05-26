-- ════════════════════════════════════════════════════════════════════════
-- SECURITY: Row-Level Security on all user-owned tables.
--
-- Before this migration NO table had RLS, while the frontend talks to
-- Supabase directly with the public anon key — so anyone with that key
-- (it ships in every browser) could read/insert/delete every row in
-- chat_sessions / chat_messages, and the same exposure applied to every
-- other user table. This locks each row to its owner via auth.uid().
--
-- The backend uses the service_role key, which has BYPASSRLS, so backend
-- ingestion / agent / artifact flows are UNAFFECTED by these policies.
-- Anonymous (logged-out) users have auth.uid() = NULL and keep their data
-- in client state only (the app never writes anon data to these tables),
-- so deny-by-default for NULL is correct.
-- ════════════════════════════════════════════════════════════════════════

-- ── chat_sessions: owner only ───────────────────────────────────────────
alter table chat_sessions enable row level security;
drop policy if exists chat_sessions_owner on chat_sessions;
create policy chat_sessions_owner on chat_sessions
  for all to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

-- ── chat_messages: scoped through the parent session's owner ────────────
alter table chat_messages enable row level security;
drop policy if exists chat_messages_owner on chat_messages;
create policy chat_messages_owner on chat_messages
  for all to authenticated
  using (session_id in (select id from chat_sessions where user_id = auth.uid()))
  with check (session_id in (select id from chat_sessions where user_id = auth.uid()));

-- ── chat_session_documents: scoped through the parent session ───────────
alter table chat_session_documents enable row level security;
drop policy if exists csd_owner on chat_session_documents;
create policy csd_owner on chat_session_documents
  for all to authenticated
  using (session_id in (select id from chat_sessions where user_id = auth.uid()))
  with check (session_id in (select id from chat_sessions where user_id = auth.uid()));

-- ── document_folders: owner only ────────────────────────────────────────
alter table document_folders enable row level security;
drop policy if exists document_folders_owner on document_folders;
create policy document_folders_owner on document_folders
  for all to authenticated
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid());

-- ── template_folders: owner only ────────────────────────────────────────
alter table template_folders enable row level security;
drop policy if exists template_folders_owner on template_folders;
create policy template_folders_owner on template_folders
  for all to authenticated
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid());

-- ── templates: owner only ───────────────────────────────────────────────
alter table templates enable row level security;
drop policy if exists templates_owner on templates;
create policy templates_owner on templates
  for all to authenticated
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid());

-- ── artifacts: owner only (anon/global artifacts have owner_id NULL and
--    are only ever served through the backend signed-URL endpoint) ───────
alter table artifacts enable row level security;
drop policy if exists artifacts_owner on artifacts;
create policy artifacts_owner on artifacts
  for all to authenticated
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid());

-- ── legal_documents: global library is public-read; user uploads are
--    private to the owner ─────────────────────────────────────────────--
alter table legal_documents enable row level security;
drop policy if exists legal_documents_read on legal_documents;
create policy legal_documents_read on legal_documents
  for select to anon, authenticated
  using (is_global = true or owner_id = auth.uid());
drop policy if exists legal_documents_write on legal_documents;
create policy legal_documents_write on legal_documents
  for all to authenticated
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid());

-- ── legal_chunks / legal_hierarchy: readable for global or owned docs.
--    (Backend search uses service_role and bypasses RLS regardless.) ─────
alter table legal_chunks enable row level security;
drop policy if exists legal_chunks_read on legal_chunks;
create policy legal_chunks_read on legal_chunks
  for select to anon, authenticated
  using (document_id in (select id from legal_documents where is_global = true or owner_id = auth.uid()));

alter table legal_hierarchy enable row level security;
drop policy if exists legal_hierarchy_read on legal_hierarchy;
create policy legal_hierarchy_read on legal_hierarchy
  for select to anon, authenticated
  using (document_id in (select id from legal_documents where is_global = true or owner_id = auth.uid()));
