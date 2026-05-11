-- Bring the schema to production parity with what the live Levy app expects.
-- Captures all the columns + tables that were applied ad-hoc to the original
-- project during phases 2-6 but were never committed as standalone migration
-- files. Replays them idempotently so this can be applied to a fresh project
-- (e.g. when migrating between Supabase organisations).

-- ─── document_folders ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS document_folders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS document_folders_owner_idx ON document_folders(owner_id);
CREATE UNIQUE INDEX IF NOT EXISTS document_folders_owner_name_idx
  ON document_folders(owner_id, lower(name));

-- ─── legal_documents — production columns ──────────────────────────────────

ALTER TABLE legal_documents
  ADD COLUMN IF NOT EXISTS is_global BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS owner_id UUID,
  ADD COLUMN IF NOT EXISTS folder_id UUID
    REFERENCES document_folders(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS pdf_storage_path TEXT,
  ADD COLUMN IF NOT EXISTS pdf_page_count INTEGER,
  ADD COLUMN IF NOT EXISTS pdf_size_bytes BIGINT,
  ADD COLUMN IF NOT EXISTS canonical_url TEXT;

CREATE INDEX IF NOT EXISTS legal_documents_owner_idx ON legal_documents(owner_id);
CREATE INDEX IF NOT EXISTS legal_documents_folder_idx ON legal_documents(folder_id);
CREATE INDEX IF NOT EXISTS legal_documents_is_global_idx ON legal_documents(is_global);

-- ─── chat_session_documents (per-thread attachment) ─────────────────────────

CREATE TABLE IF NOT EXISTS chat_session_documents (
  session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  document_id UUID NOT NULL REFERENCES legal_documents(id) ON DELETE CASCADE,
  attached_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (session_id, document_id)
);

CREATE INDEX IF NOT EXISTS chat_session_documents_session_idx
  ON chat_session_documents(session_id);

-- ─── chat_messages — rich-content columns ───────────────────────────────────

ALTER TABLE chat_messages
  ADD COLUMN IF NOT EXISTS blocks JSONB,
  ADD COLUMN IF NOT EXISTS tool_calls JSONB,
  ADD COLUMN IF NOT EXISTS citations JSONB,
  ADD COLUMN IF NOT EXISTS web_sources JSONB,
  ADD COLUMN IF NOT EXISTS artifacts JSONB,
  ADD COLUMN IF NOT EXISTS compaction JSONB;

-- ─── artifacts (agent-generated PDFs) ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS artifacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID,
  session_id UUID REFERENCES chat_sessions(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  kind TEXT NOT NULL,                -- 'pdf' | 'docx' | 'md' | 'txt'
  source TEXT NOT NULL,              -- 'generated' | 'extracted' | 'merged' | 'uploaded'
  storage_path TEXT NOT NULL,        -- '<bucket>/<key>'
  page_count INTEGER,
  size_bytes BIGINT,
  meta JSONB DEFAULT '{}'::jsonb,
  archived_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS artifacts_owner_idx ON artifacts(owner_id);
CREATE INDEX IF NOT EXISTS artifacts_session_idx ON artifacts(session_id);
CREATE INDEX IF NOT EXISTS artifacts_created_idx ON artifacts(created_at);

-- ─── legal_documents.short_name (used in citation rendering) ────────────────

ALTER TABLE legal_documents ADD COLUMN IF NOT EXISTS short_name TEXT;

-- ─── search_legal_chunks_scoped RPC (visibility-aware vector search) ────────
-- Returns chunks that are either global, owned by caller, or attached to the
-- current chat session. The backend calls it via `db.rpc(...)`.

CREATE OR REPLACE FUNCTION search_legal_chunks_scoped(
  query_embedding vector(768),
  match_count INTEGER,
  match_threshold FLOAT,
  caller_user_id UUID DEFAULT NULL,
  attached_doc_ids UUID[] DEFAULT ARRAY[]::UUID[]
)
RETURNS TABLE (
  id UUID,
  document_id UUID,
  content TEXT,
  metadata JSONB,
  page_start INTEGER,
  page_end INTEGER,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    c.id,
    c.document_id,
    c.content,
    c.metadata,
    c.page_start,
    c.page_end,
    (1 - (c.embedding <=> query_embedding))::FLOAT AS similarity
  FROM legal_chunks c
  JOIN legal_documents d ON d.id = c.document_id
  WHERE
    (1 - (c.embedding <=> query_embedding)) >= match_threshold
    AND (
      d.is_global IS TRUE
      OR (caller_user_id IS NOT NULL AND d.owner_id = caller_user_id)
      OR d.id = ANY(attached_doc_ids)
    )
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- ─── Storage buckets (private) ──────────────────────────────────────────────

INSERT INTO storage.buckets (id, name, public)
VALUES ('legal-docs', 'legal-docs', false)
ON CONFLICT (id) DO NOTHING;

INSERT INTO storage.buckets (id, name, public)
VALUES ('artifacts', 'artifacts', false)
ON CONFLICT (id) DO NOTHING;
