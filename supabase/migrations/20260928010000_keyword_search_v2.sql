-- Keyword search v2: bounded work per search. Additive: v1 stays, so
-- switching back is a config change (HYBRID_KEYWORD_RPC), not a migration.
--
-- WHY. v1 was correct and too slow. Measured on the live database on
-- 28 September 2026, time tracked how common the query's words were, not how
-- many there were: "gratuity" 0.6 s, "employer" 2.4 s, "person" 7.1 s, and
-- the gold question env-01 hit the 8 s statement timeout. Two costs scale
-- with a word's frequency, and a small instance does not keep the index in
-- memory, so each one is disk reads:
--
--   1. v1 ran count(*) over the index for EVERY query word, on every
--      search, to get its document frequency: up to 34,000 rows visited for
--      one gold question before ranking even started.
--   2. The candidate set was every chunk holding one of the three rarest
--      words. When those are still common ("environmental", "purpose",
--      "management") that is 11,882 chunks to score for env-01.
--
-- WHAT CHANGED.
--   1. Document frequencies are computed once, into legal_lexeme_stats, by
--      ts_stat. A word missing from it (new since the last refresh) is
--      counted live, which is cheap because such a word is rare.
--   2. Candidates come from the rarest words only until their frequencies
--      add up to 3,000 (the rarest word is always used), and a query whose
--      rarest word is in more than 6,000 chunks gets no keyword results at
--      all. Tested on the same 126,821 chunks in a local copy: right Act,
--      right section and expected-term rates identical to v1 (62% / 25% /
--      79%); 21 of 24 top-five score lists identical, the other three losing
--      v1's first chunk to a chunk matching the rare word; worst candidate
--      set 11,882 -> 3,262.
--   3. (From the first v2 draft) the ranked shortlist is materialised and
--      limited before chunk text and vectors are fetched, so content and a
--      768-dimension vector are read for 30 rows, not thousands.
--
-- Postgres full-text ranking is still not BM25; each word is weighted by
-- BM25's IDF and its ts_rank summed, as in v1.
--
-- HOW TO RUN (Supabase SQL editor): the whole file. Step 4 reads the lexeme
-- table once and may take a minute; if it times out, run it again on its own.

BEGIN;

-- ── 1. Document frequency per lexeme. Locked like legal_chunk_lexemes: RLS
--      on and no policies, because it includes words from private uploads.
CREATE TABLE IF NOT EXISTS public.legal_lexeme_stats (
  lexeme TEXT PRIMARY KEY,
  df     INTEGER NOT NULL
);
ALTER TABLE public.legal_lexeme_stats ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.legal_lexeme_stats FROM anon, authenticated;

-- ── 2. Refresh function. Run it again after a large
--      ingest; a stale count only shifts a weight slightly, and a word it
--      has never seen is counted live.
CREATE OR REPLACE FUNCTION public.refresh_legal_lexeme_stats()
RETURNS INTEGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
  written INTEGER;
BEGIN
  INSERT INTO public.legal_lexeme_stats (lexeme, df)
  SELECT word, ndoc FROM ts_stat('SELECT tsv FROM public.legal_chunk_lexemes')
  ON CONFLICT (lexeme) DO UPDATE SET df = EXCLUDED.df;
  GET DIAGNOSTICS written = ROW_COUNT;
  ANALYZE public.legal_lexeme_stats;
  RETURN written;
END;
$$;
REVOKE ALL ON FUNCTION public.refresh_legal_lexeme_stats() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.refresh_legal_lexeme_stats() TO service_role;

-- ── 3. The search. Same arguments, same visibility rules and same result
--      columns as v1.
CREATE OR REPLACE FUNCTION public.search_legal_chunks_keyword_v2(
  query_text TEXT,
  query_embedding vector(768) DEFAULT NULL,
  match_count INTEGER DEFAULT 30,
  caller_user_id UUID DEFAULT NULL,
  attached_doc_ids UUID[] DEFAULT ARRAY[]::UUID[]
)
RETURNS TABLE (
  id UUID, document_id UUID, content TEXT, metadata JSONB,
  page_start INTEGER, page_end INTEGER, similarity FLOAT, keyword_rank FLOAT
)
LANGUAGE plpgsql STABLE
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
  n FLOAT;
  terms TEXT[] := ARRAY[]::TEXT[];
  weights FLOAT[] := ARRAY[]::FLOAT[];
  dfs BIGINT[] := ARRAY[]::BIGINT[];
  queries TSQUERY[] := ARRAY[]::TSQUERY[];
  gate TSQUERY;
  t TEXT;
  tq TSQUERY;
  df BIGINT;
  take_count INTEGER := greatest(0, least(coalesce(match_count, 30), 100));
  budget CONSTANT BIGINT := 3000;
  -- The rarest word always joins the gate, so a query of common words only
  -- ("person" on its own: about 20,000 chunks, 7.1 s on v1) would still scan
  -- them all. Keyword ranking adds nothing to a query that generic; return
  -- nothing and let the vector search carry it. The largest rarest-word
  -- frequency among the 24 gold questions is 3,262.
  rarest_cap CONSTANT BIGINT := 6000;
BEGIN
  IF take_count = 0 OR btrim(coalesce(query_text, '')) = '' THEN RETURN; END IF;
  SELECT greatest(reltuples, 1) INTO n
  FROM pg_class WHERE oid = 'public.legal_chunk_lexemes'::regclass;
  IF n IS NULL OR n <= 1 THEN
    SELECT greatest(count(*), 1) INTO n FROM public.legal_chunk_lexemes;
  END IF;

  FOR t IN
    SELECT lexeme FROM unnest(to_tsvector('english', query_text)) LIMIT 16
  LOOP
    tq := quote_literal(t)::tsquery;
    SELECT s.df INTO df FROM public.legal_lexeme_stats s WHERE s.lexeme = t;
    IF NOT FOUND THEN
      -- New since the last refresh, so rare: a short posting list to count.
      SELECT count(*) INTO df FROM public.legal_chunk_lexemes l WHERE l.tsv @@ tq;
    END IF;
    IF df > 0 AND df < n / 5 THEN
      terms   := terms || t;
      dfs     := dfs || df;
      queries := array_append(queries, tq);
      weights := weights || ln(1 + (n - df + 0.5) / (df + 0.5));
    END IF;
  END LOOP;
  IF coalesce(array_length(terms, 1), 0) = 0 THEN RETURN; END IF;
  IF (SELECT min(x) FROM unnest(dfs) AS x) > rarest_cap THEN RETURN; END IF;

  -- Rarest words first, until their frequencies pass the budget.
  SELECT string_agg(quote_literal(g.tm), ' | ')::tsquery INTO gate
  FROM (
    SELECT u.tm,
           row_number() OVER (ORDER BY u.df, u.tm) AS rn,
           sum(u.df) OVER (ORDER BY u.df, u.tm ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running
    FROM unnest(terms, dfs) AS u(tm, df)
  ) g
  WHERE g.rn = 1 OR g.running <= budget;

  RETURN QUERY
  WITH ranked AS MATERIALIZED (
    SELECT l.chunk_id,
           (SELECT sum(u.w * ts_rank(l.tsv, u.q, 1))
            FROM unnest(queries, weights) AS u(q, w)) AS score
    FROM public.legal_chunk_lexemes l
    JOIN public.legal_documents d ON d.id = l.document_id
    WHERE l.tsv @@ gate
      AND (d.is_global IS TRUE
        OR (caller_user_id IS NOT NULL AND d.owner_id = caller_user_id)
        OR d.id = ANY(coalesce(attached_doc_ids, ARRAY[]::UUID[])))
    ORDER BY score DESC, l.chunk_id
    LIMIT take_count
  )
  SELECT lc.id, lc.document_id, lc.content, lc.metadata, lc.page_start, lc.page_end,
         CASE WHEN query_embedding IS NULL THEN NULL
              ELSE (1 - (lc.embedding <=> query_embedding))::FLOAT END,
         r.score::FLOAT
  FROM ranked r JOIN public.legal_chunks lc ON lc.id = r.chunk_id
  ORDER BY r.score DESC, r.chunk_id;
END;
$$;
REVOKE ALL ON FUNCTION public.search_legal_chunks_keyword_v2(TEXT, vector, INTEGER, UUID, UUID[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.search_legal_chunks_keyword_v2(TEXT, vector, INTEGER, UUID, UUID[]) TO service_role;

COMMIT;

-- ── 4. First fill, outside the transaction on purpose: if it times out, the
--      function above still works and counts each word live (v1's speed)
--      until this is run again. Returns the number of lexemes written.
SELECT public.refresh_legal_lexeme_stats();

-- Check, then compare with v1 (the same rows at the top, much faster on
-- common words):
-- SELECT left(content, 70), keyword_rank FROM search_legal_chunks_keyword_v2('person', NULL, 5);
