"""Grounded search must survive a total embedding outage.

OpenAI credit has run out three times since August 2026, and each outage took
every grounded search down while chat kept answering from memory. OpenRouter
has no embeddings endpoint and Moonshot's is closed (checked 6 Oct 2026), and
the Gemini second space was 99.7% unfilled, so the only full-coverage fallback
is the keyword index, which needs no vector at all.
"""
import asyncio
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services import tools  # noqa: E402


def _down(query):
    raise RuntimeError("insufficient_quota")


def kw_row(cid, doc, section, rank, doc_type="act"):
    return {"id": cid, "document_id": doc, "content": f"text {cid}", "similarity": None,
            "keyword_rank": rank,
            "metadata": {"act_name": f"Act {doc}", "section_number": section, "document_type": doc_type}}


class CorpusSearch(unittest.IsolatedAsyncioTestCase):
    async def search(self, rows):
        calls = {}

        def fake_keyword(query, embedding, top_k, **kw):
            calls.update(embedding=embedding, rpc=kw.get("rpc_name"))
            return rows

        with patch.object(tools, "get_query_embedding_ex", _down), \
                patch.object(tools, "search_keyword", fake_keyword):
            out = await tools._search_corpus("gratuity on resignation", top_k=3)
        return out["result"], calls

    async def test_keyword_ranking_carries_the_search(self):
        r, calls = await self.search([kw_row("a", "d1", "54", 9.1), kw_row("b", "d2", "12", 4.2)])
        self.assertEqual(r["retrieval"], "keyword_only")
        self.assertIsNone(calls["embedding"])          # no vector was needed
        self.assertIn("MEANING-BASED SEARCH IS DOWN", r["retrieval_warning"])
        self.assertEqual([m["chunk_id"] for m in r["matches"]], ["a", "b"])  # rank order kept
        self.assertEqual(r["matches"][0]["similarity"], 0.0)  # NULL similarity must not crash
        self.assertNotIn("library_miss", r)            # a 0.0 "similarity" is not a miss here

    async def test_nothing_found_is_a_miss_that_forbids_memory(self):
        r, _ = await self.search([])
        self.assertTrue(r["library_miss"])
        self.assertIn("Do not answer from memory", r["next_step"])


class CaseLawSearch(unittest.IsolatedAsyncioTestCase):
    async def test_judgments_still_searchable(self):
        rows = [kw_row("j1", "doc-j", "", 7.0, doc_type="judgment"), kw_row("x", "doc-a", "4", 6.0)]
        with patch.object(tools, "get_query_embedding_ex", _down), \
                patch.object(tools, "search_keyword", lambda *a, **k: rows), \
                patch("app.db.supabase.get_db", side_effect=RuntimeError("no db in tests")):
            out = await tools._search_case_law("circumstantial evidence")
        matches = out["result"]["matches"]
        self.assertEqual([m["document_id"] for m in matches], ["doc-j"])
        self.assertEqual(matches[0]["similarity"], 0.0)


class NormalPathUntouched(unittest.IsolatedAsyncioTestCase):
    async def test_embeddings_up_means_no_keyword_only(self):
        with patch.object(tools, "get_query_embedding_ex", lambda q: {"vector": [0.0], "space": "gemini"}), \
                patch.object(tools, "search_chunks", lambda *a, **k: []):
            out = await tools._search_corpus("anything", top_k=3)
        self.assertEqual(out["result"]["retrieval"], "dense")


if __name__ == "__main__":
    unittest.main()
