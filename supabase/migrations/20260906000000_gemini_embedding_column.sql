-- Cross-vendor embedding redundancy.
--
-- The corpus is embedded with OpenAI text-embedding-3-small (768d). When that
-- account fails (it has, twice: credit exhaustion), ALL search fails, because
-- vectors from any other model are incompatible with the stored ones and a
-- cross-model query returns confidently wrong matches.
--
-- The correct redundancy is a SECOND EMBEDDING SPACE: every chunk also gets a
-- gemini-embedding-001 vector (768d, free tier), and a mirrored search
-- function that compares Gemini queries only against Gemini vectors. The two
-- spaces never mix. The backend falls over to the Gemini path only when the
-- OpenAI route (primary and fallback key alike) is down, and only for chunks
-- that have the second vector.

ALTER TABLE legal_chunks ADD COLUMN IF NOT EXISTS embedding_gemini VECTOR(768);

-- HNSW like the primary column; partial-safe because NULLs are simply absent
-- from the index.
CREATE INDEX IF NOT EXISTS legal_chunks_embedding_gemini_idx
  ON legal_chunks USING hnsw (embedding_gemini vector_cosine_ops);

DROP FUNCTION IF EXISTS search_legal_chunks_gemini;
CREATE FUNCTION search_legal_chunks_gemini(
  query_embedding VECTOR(768),
  match_count INTEGER DEFAULT 5,
  match_threshold FLOAT DEFAULT 0.7
)
RETURNS TABLE (
  id UUID,
  content TEXT,
  summary TEXT,
  metadata JSONB,
  document_id UUID,
  hierarchy_id UUID,
  page_start INTEGER,
  page_end INTEGER,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    lc.id,
    lc.content,
    lc.summary,
    lc.metadata,
    lc.document_id,
    lc.hierarchy_id,
    lc.page_start,
    lc.page_end,
    (1 - (lc.embedding_gemini <=> query_embedding))::FLOAT AS similarity
  FROM legal_chunks lc
  WHERE lc.effective_to IS NULL
    AND lc.embedding_gemini IS NOT NULL
    AND 1 - (lc.embedding_gemini <=> query_embedding) > match_threshold
  ORDER BY lc.embedding_gemini <=> query_embedding
  LIMIT match_count;
END;
$$;

-- The production search path is the visibility-aware scoped function; mirror
-- it for the Gemini space (identical visibility rules, gemini column only).
CREATE OR REPLACE FUNCTION search_legal_chunks_scoped_gemini(
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
    (1 - (c.embedding_gemini <=> query_embedding))::FLOAT AS similarity
  FROM legal_chunks c
  JOIN legal_documents d ON d.id = c.document_id
  WHERE
    c.embedding_gemini IS NOT NULL
    AND (1 - (c.embedding_gemini <=> query_embedding)) >= match_threshold
    AND (
      d.is_global IS TRUE
      OR (caller_user_id IS NOT NULL AND d.owner_id = caller_user_id)
      OR d.id = ANY(attached_doc_ids)
    )
  ORDER BY c.embedding_gemini <=> query_embedding
  LIMIT match_count;
END;
$$;
