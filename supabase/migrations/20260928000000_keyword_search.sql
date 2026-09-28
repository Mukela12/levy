-- Keyword search beside vector search.
--
-- Measured on 28 September 2026 over the 16 gold questions whose expected Act
-- is still law: pgvector alone put the right Act in the top five 31% of the
-- time, because it prefers the repealed predecessors that read almost the
-- same (the Environmental Protection and Pollution Control Act over the
-- Environmental Management Act, the Employment Act over the Employment Code).
-- BM25 over the same chunks found it 75% of the time; fused with the vectors,
-- 69%, with the right SECTION rising from 19% to 31%. See bench/retrieval_eval.py.
--
-- Postgres full-text ranking is not BM25: ts_rank has no inverse document
-- frequency, so "employee" would count as much as "gratuity". The function
-- below weights each query term by BM25's IDF and sums per-term ranks, which
-- gets close. It is measured separately before it is switched on.
--
-- WHY A SEPARATE TABLE. Adding a tsvector column to legal_chunks and
-- backfilling it would write a new version of every row, and each new version
-- has to go back into the HNSW vector index that every search depends on:
-- slow on ~130k rows, and it bloats that index. This table references chunks
-- and never writes to legal_chunks.
--
-- HOW TO RUN (Supabase SQL editor). Run the whole file. If step 3 times out,
-- run just the batched statement in step 3 again until it inserts 0 rows,
-- then run steps 4 and 5.

-- ── 1. The table. Locked: RLS on and no policies, so only the service role
--      (the backend, which bypasses RLS) can read it. It holds lexemes of
--      private uploads too, and Supabase exposes public tables over REST.
CREATE TABLE IF NOT EXISTS legal_chunk_lexemes (
  chunk_id    UUID PRIMARY KEY REFERENCES legal_chunks(id) ON DELETE CASCADE,
  document_id UUID NOT NULL,
  tsv         TSVECTOR NOT NULL
);
ALTER TABLE legal_chunk_lexemes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON legal_chunk_lexemes FROM anon, authenticated;

-- ── 2. Keep it in step with legal_chunks. Created before the backfill so a
--      chunk ingested while it runs is not missed.
CREATE OR REPLACE FUNCTION legal_chunk_lexemes_sync() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO legal_chunk_lexemes (chunk_id, document_id, tsv)
  VALUES (NEW.id, NEW.document_id, to_tsvector('english', coalesce(NEW.content, '')))
  ON CONFLICT (chunk_id) DO UPDATE
    SET document_id = EXCLUDED.document_id, tsv = EXCLUDED.tsv;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS legal_chunk_lexemes_sync ON legal_chunks;
CREATE TRIGGER legal_chunk_lexemes_sync
  AFTER INSERT OR UPDATE OF content, document_id ON legal_chunks
  FOR EACH ROW EXECUTE FUNCTION legal_chunk_lexemes_sync();

-- ── 3. Backfill, in batches so no single statement runs long. Repeat until
--      it reports INSERT 0 0.
INSERT INTO legal_chunk_lexemes (chunk_id, document_id, tsv)
SELECT c.id, c.document_id, to_tsvector('english', coalesce(c.content, ''))
FROM legal_chunks c
WHERE NOT EXISTS (SELECT 1 FROM legal_chunk_lexemes l WHERE l.chunk_id = c.id)
LIMIT 40000
ON CONFLICT (chunk_id) DO NOTHING;

INSERT INTO legal_chunk_lexemes (chunk_id, document_id, tsv)
SELECT c.id, c.document_id, to_tsvector('english', coalesce(c.content, ''))
FROM legal_chunks c
WHERE NOT EXISTS (SELECT 1 FROM legal_chunk_lexemes l WHERE l.chunk_id = c.id)
LIMIT 40000
ON CONFLICT (chunk_id) DO NOTHING;

INSERT INTO legal_chunk_lexemes (chunk_id, document_id, tsv)
SELECT c.id, c.document_id, to_tsvector('english', coalesce(c.content, ''))
FROM legal_chunks c
WHERE NOT EXISTS (SELECT 1 FROM legal_chunk_lexemes l WHERE l.chunk_id = c.id)
LIMIT 40000
ON CONFLICT (chunk_id) DO NOTHING;

INSERT INTO legal_chunk_lexemes (chunk_id, document_id, tsv)
SELECT c.id, c.document_id, to_tsvector('english', coalesce(c.content, ''))
FROM legal_chunks c
WHERE NOT EXISTS (SELECT 1 FROM legal_chunk_lexemes l WHERE l.chunk_id = c.id)
LIMIT 40000
ON CONFLICT (chunk_id) DO NOTHING;

-- ── 4. Indexes, built once after the backfill rather than maintained through it.
CREATE INDEX IF NOT EXISTS legal_chunk_lexemes_tsv_idx ON legal_chunk_lexemes USING gin (tsv);
CREATE INDEX IF NOT EXISTS legal_chunk_lexemes_doc_idx ON legal_chunk_lexemes (document_id);
ANALYZE legal_chunk_lexemes;

-- ── 5. The search. Same visibility rules as search_legal_chunks_scoped: the
--      global library, the caller's own uploads, and this thread's
--      attachments, nothing else.
--
--      Each query term is weighted by BM25's inverse document frequency and
--      its ts_rank (normalised by document length) summed, so a rare term
--      that names the subject outweighs a common one. Terms found in more
--      than a fifth of the library are dropped: they say nothing about this
--      question and would make the candidate set the whole table.
--
--      Returns each hit's cosine similarity to the query vector as well, so
--      a keyword-only match carries the same score field as a vector match.
CREATE OR REPLACE FUNCTION search_legal_chunks_keyword(
  query_text       TEXT,
  query_embedding  vector(768) DEFAULT NULL,
  match_count      INTEGER DEFAULT 30,
  caller_user_id   UUID DEFAULT NULL,
  attached_doc_ids UUID[] DEFAULT ARRAY[]::UUID[]
)
RETURNS TABLE (
  id            UUID,
  document_id   UUID,
  content       TEXT,
  metadata      JSONB,
  page_start    INTEGER,
  page_end      INTEGER,
  similarity    FLOAT,
  keyword_rank  FLOAT
)
LANGUAGE plpgsql STABLE
AS $$
DECLARE
  n         FLOAT;
  terms     TEXT[] := ARRAY[]::TEXT[];
  weights   FLOAT[] := ARRAY[]::FLOAT[];
  any_query TSQUERY;
  t         TEXT;
  df        BIGINT;
BEGIN
  SELECT greatest(reltuples, 1) INTO n FROM pg_class WHERE relname = 'legal_chunk_lexemes';
  IF n IS NULL OR n <= 1 THEN
    SELECT greatest(count(*), 1) INTO n FROM legal_chunk_lexemes;
  END IF;

  -- The question's own lexemes, after english stemming and stop words.
  FOR t IN
    SELECT lexeme FROM unnest(to_tsvector('english', coalesce(query_text, ''))) LIMIT 16
  LOOP
    -- Already a lexeme: cast, do not stem it a second time.
    SELECT count(*) INTO df FROM legal_chunk_lexemes l WHERE l.tsv @@ quote_literal(t)::tsquery;
    IF df > 0 AND df < n / 5 THEN
      terms   := terms   || t;
      weights := weights || ln(1 + (n - df + 0.5) / (df + 0.5));
    END IF;
  END LOOP;

  IF coalesce(array_length(terms, 1), 0) = 0 THEN
    RETURN;
  END IF;

  -- Candidates must contain at least one of the three rarest terms. A chunk
  -- matching only common ones cannot reach the top under IDF weighting, and
  -- without this a broad question scores tens of thousands of rows.
  SELECT string_agg(quote_literal(x.tm), ' | ')::tsquery INTO any_query
  FROM (SELECT u.tm FROM unnest(terms, weights) AS u(tm, w) ORDER BY u.w DESC LIMIT 3) AS x;

  RETURN QUERY
  WITH cand AS (
    SELECT l.chunk_id, l.tsv
    FROM legal_chunk_lexemes l
    JOIN legal_documents d ON d.id = l.document_id
    WHERE l.tsv @@ any_query
      AND (
        d.is_global IS TRUE
        OR (caller_user_id IS NOT NULL AND d.owner_id = caller_user_id)
        OR d.id = ANY(attached_doc_ids)
      )
  ),
  scored AS (
    SELECT c.chunk_id,
           (SELECT sum(u.w * ts_rank(c.tsv, quote_literal(u.tm)::tsquery, 1))
              FROM unnest(terms, weights) AS u(tm, w)) AS score
    FROM cand c
  )
  SELECT lc.id, lc.document_id, lc.content, lc.metadata, lc.page_start, lc.page_end,
         CASE WHEN query_embedding IS NULL THEN NULL
              ELSE (1 - (lc.embedding <=> query_embedding))::FLOAT END,
         s.score::FLOAT
  FROM scored s
  JOIN legal_chunks lc ON lc.id = s.chunk_id
  ORDER BY s.score DESC
  LIMIT match_count;
END;
$$;

REVOKE ALL ON FUNCTION search_legal_chunks_keyword(TEXT, vector, INTEGER, UUID, UUID[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION search_legal_chunks_keyword(TEXT, vector, INTEGER, UUID, UUID[]) TO service_role;

-- Check (should return 5 rows about meal breaks from the Employment Code):
-- SELECT left(content, 80), keyword_rank FROM search_legal_chunks_keyword('meal break health break working day');
