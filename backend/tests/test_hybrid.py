"""Vector and keyword results fused, and the path that stays unchanged when it is off."""
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services import hybrid, tools


def row(rid, sim=None, doc="d-live"):
    return {"id": rid, "document_id": doc, "content": f"text {rid}", "metadata": {},
            "page_start": 1, "page_end": 1, "similarity": sim}


class Fusion(unittest.TestCase):
    def test_agreement_rises(self):
        dense = [row("a", .9), row("b", .8), row("c", .7)]
        keyword = [row("c", .5), row("d", .4), row("a", .9)]
        order = [r["id"] for r in hybrid.rrf(dense, keyword)]
        # a and c are in both lists; a ranks first in one and third in the other.
        self.assertEqual(order[:2], ["a", "c"])
        self.assertEqual(set(order), {"a", "b", "c", "d"})

    def test_a_row_found_by_one_method_survives(self):
        order = [r["id"] for r in hybrid.rrf([row("a")], [row("z")])]
        self.assertIn("z", order)

    def test_each_row_appears_once(self):
        fused = hybrid.rrf([row("a"), row("a")], [row("a")])
        self.assertEqual(len(fused), 1)

    def test_every_row_carries_a_similarity(self):
        fused = hybrid.fuse([row("a", .7)], [row("k", None)])
        self.assertTrue(all(isinstance(r["similarity"], float) for r in fused))

    def test_ties_break_the_same_way_every_run(self):
        a = [r["id"] for r in hybrid.rrf([row("x")], [row("y")])]
        b = [r["id"] for r in hybrid.rrf([row("x")], [row("y")])]
        self.assertEqual(a, b)


def settings(**kw):
    base = dict(similarity_threshold=0.6, hybrid_retrieval_enabled=False,
                hybrid_keyword_rpc="search_legal_chunks_keyword",
                hybrid_candidates=30, hybrid_dense_threshold=0.3)
    base.update(kw)
    return SimpleNamespace(**base)


class SearchCorpus(unittest.IsolatedAsyncioTestCase):
    def patches(self, s, dense, keyword):
        kw = MagicMock(return_value=keyword)
        ps = [patch.object(tools, "get_settings", lambda: s),
              patch.object(tools, "get_query_embedding_ex", lambda q: {"vector": [0.0] * 4, "space": "openai"}),
              patch.object(tools, "search_chunks", MagicMock(return_value=dense)),
              patch.object(tools, "search_keyword", kw)]
        for p in ps:
            p.start()
            self.addCleanup(p.stop)
        return kw

    async def test_off_is_the_old_path(self):
        kw = self.patches(settings(), [row("b", .7), row("a", .9)], [row("k", .5)])
        out = await tools._search_corpus("meal break", top_k=2)
        kw.assert_not_called()
        # The dense-only path still sorts by cosine.
        self.assertEqual([m["chunk_id"] for m in out["result"]["matches"]], ["a", "b"])

    async def test_on_keeps_the_fused_order(self):
        dense = [row("a", .9), row("b", .8), row("c", .7)]
        keyword = [row("c", .5), row("k", .45)]
        self.patches(settings(hybrid_retrieval_enabled=True), dense, keyword)
        out = await tools._search_corpus("meal break", top_k=3)
        ids = [m["chunk_id"] for m in out["result"]["matches"]]
        # c is in both lists, so it leads despite the lowest cosine. Sorted by
        # cosine the answer would be a, b, c: the fusion would be undone.
        self.assertEqual(ids, ["c", "a", "b"])

    async def test_versioned_keyword_rpc_preserves_caller_scope(self):
        kw = self.patches(settings(hybrid_retrieval_enabled=True,
                                  hybrid_keyword_rpc="search_legal_chunks_keyword_v2"),
                          [row("a", .8)], [row("a", .8)])
        await tools._search_corpus("meal break", caller_user_id="owner", attached_doc_ids=["attachment"])
        kw.assert_called_once_with("meal break", [0.0] * 4, 30,
                                   caller_user_id="owner", attached_doc_ids=["attachment"],
                                   rpc_name="search_legal_chunks_keyword_v2")

    async def test_a_missing_keyword_function_falls_back_to_vectors(self):
        self.patches(settings(hybrid_retrieval_enabled=True), [row("a", .9), row("b", .8)], [])
        out = await tools._search_corpus("meal break", top_k=2)
        self.assertEqual({m["chunk_id"] for m in out["result"]["matches"]}, {"a", "b"})

    async def test_keyword_failure_gives_the_normal_result_without_a_second_call(self):
        # The loose list is the top 30 by cosine, so its rows at the normal
        # threshold are exactly the normal result: the 0.35 row must not leak.
        self.patches(settings(hybrid_retrieval_enabled=True), [], [])
        tools.search_chunks.side_effect = [[row("a", .9), row("b", .7), row("loose", .35)]]
        out = await tools._search_corpus(
            "meal break", top_k=2, caller_user_id="owner", attached_doc_ids=["attached"])
        self.assertEqual([m["chunk_id"] for m in out["result"]["matches"]], ["a", "b"])
        self.assertEqual(tools.search_chunks.call_count, 1)

    async def test_a_bigger_request_than_the_loose_list_asks_again(self):
        # top_k 12 needs 36 candidates; the loose list holds 30, so the normal
        # query must run with its own parameters and the caller's scope.
        self.patches(settings(hybrid_retrieval_enabled=True), [], [])
        tools.search_chunks.side_effect = [
            [row("a", .9), row("loose", .35)],
            [row("a", .9)],
        ]
        await tools._search_corpus(
            "meal break", top_k=12, caller_user_id="owner", attached_doc_ids=["attached"])
        self.assertEqual(tools.search_chunks.call_count, 2)
        tools.search_chunks.assert_called_with(
            [0.0] * 4, top_k=36, threshold=.6,
            caller_user_id="owner", attached_doc_ids=["attached"], space="openai")

    async def test_the_library_miss_signal_still_works(self):
        self.patches(settings(hybrid_retrieval_enabled=True), [row("a", .40)], [row("k", .35)])
        out = await tools._search_corpus("something the library lacks", top_k=2)
        self.assertTrue(out["result"].get("library_miss"))


if __name__ == "__main__":
    unittest.main()
