-- Update vector dimensions from 1024 to 768 for local BGE model
-- Voyage AI free tier hit rate limits, using local model as primary
-- Can re-migrate to 1024 when Voyage billing is activated

-- Drop the HNSW index first
DROP INDEX IF EXISTS idx_chunks_embedding;

-- Alter the column to 768 dimensions
ALTER TABLE legal_chunks DROP COLUMN IF EXISTS embedding;
ALTER TABLE legal_chunks ADD COLUMN embedding VECTOR(768);

-- Recreate the HNSW index
CREATE INDEX idx_chunks_embedding ON legal_chunks
  USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- Drop old function (parameter type changed)
DROP FUNCTION IF EXISTS search_legal_chunks;

-- Recreate search function with 768 dimensions
CREATE FUNCTION search_legal_chunks(
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
    (1 - (lc.embedding <=> query_embedding))::FLOAT AS similarity
  FROM legal_chunks lc
  WHERE lc.effective_to IS NULL
    AND 1 - (lc.embedding <=> query_embedding) > match_threshold
  ORDER BY lc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
