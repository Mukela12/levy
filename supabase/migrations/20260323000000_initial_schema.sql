-- Levy Legal AI — Database Schema
-- Run this in Supabase SQL Editor to set up the database

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Acts and their metadata
CREATE TABLE IF NOT EXISTS legal_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  short_name TEXT,
  act_number TEXT,
  year INTEGER,
  effective_date DATE,
  document_type TEXT DEFAULT 'act',
  source_url TEXT,
  pdf_hash TEXT,
  total_sections INTEGER,
  total_chunks INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Hierarchical structure: Act → Part → Chapter → Section → Subsection
CREATE TABLE IF NOT EXISTS legal_hierarchy (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES legal_documents(id) ON DELETE CASCADE,
  parent_id UUID REFERENCES legal_hierarchy(id) ON DELETE CASCADE,
  level TEXT NOT NULL,
  number TEXT,
  title TEXT,
  sort_order INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chunks with embeddings for vector search
CREATE TABLE IF NOT EXISTS legal_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES legal_documents(id) ON DELETE CASCADE,
  hierarchy_id UUID REFERENCES legal_hierarchy(id) ON DELETE SET NULL,
  content TEXT NOT NULL,
  summary TEXT,
  embedding VECTOR(1536),
  metadata JSONB DEFAULT '{}',
  effective_from DATE,
  effective_to DATE,
  chunk_index INTEGER DEFAULT 0,
  page_start INTEGER,
  page_end INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Amendment tracking
CREATE TABLE IF NOT EXISTS amendments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  original_chunk_id UUID REFERENCES legal_chunks(id) ON DELETE CASCADE,
  amended_chunk_id UUID REFERENCES legal_chunks(id) ON DELETE SET NULL,
  amendment_act TEXT,
  amendment_date DATE,
  change_type TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Cross-references between sections/acts
CREATE TABLE IF NOT EXISTS cross_references (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_chunk_id UUID REFERENCES legal_chunks(id) ON DELETE CASCADE,
  target_chunk_id UUID REFERENCES legal_chunks(id) ON DELETE SET NULL,
  relationship TEXT,
  context TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chat history
CREATE TABLE IF NOT EXISTS chat_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID,
  title TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  citations JSONB DEFAULT '[]',
  provider TEXT,
  model TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_chunks_document ON legal_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_hierarchy ON legal_chunks(hierarchy_id);
CREATE INDEX IF NOT EXISTS idx_hierarchy_document ON legal_hierarchy(document_id);
CREATE INDEX IF NOT EXISTS idx_hierarchy_parent ON legal_hierarchy(parent_id);

-- pgvector similarity search index (HNSW — supports 3072 dims, faster queries than IVFFlat)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON legal_chunks
  USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- Helper function: search similar chunks
CREATE OR REPLACE FUNCTION search_legal_chunks(
  query_embedding VECTOR(1536),
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
    1 - (lc.embedding <=> query_embedding) AS similarity
  FROM legal_chunks lc
  WHERE lc.effective_to IS NULL  -- only current law
    AND 1 - (lc.embedding <=> query_embedding) > match_threshold
  ORDER BY lc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
