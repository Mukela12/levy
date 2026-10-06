"""Passed is not in force, and a dead section is not live law.

Found by the benchmark of 28 Sep and its re-test on 5 Oct 2026: asked which
law governs a work permit, Levy led with the Immigration Control Act, 2026,
which starts on a date set by statutory instrument and had no commencement
order, and its source panel still offered section 24 of the Immigration and
Deportation Act 2010, repealed in 2016, as if it were law.
"""
import asyncio
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services import citation_audit, law_map, tools  # noqa: E402

OLD = "immigration-2010"
NEW = "immigration-2026"
AMENDER = {"op": "repealed", "by_id": "amend-2016", "by_title": "The Immigration and Deportation (Amendment)",
           "by_number": "No. 19 of 2016", "by_year": 2016, "confidence": "high", "evidence": "repeal of section 24"}
ENTRIES = {
    OLD: {"status": "repeal pending", "title": "The Immigration and Deportation 2010", "year": 2010,
          "repeal_pending_by": [{"id": NEW, "title": "The Immigration Control Act, 2026"}]},
    NEW: {"status": "commencement pending", "title": "The Immigration Control Act, 2026", "year": 2026,
          "will_repeal": [{"id": OLD, "title": "The Immigration and Deportation 2010"},
                          {"id": "imm-cap", "title": "REPUBLIC OF ZAMBIA THE IMMIGRATION AND DEPORTATION ACT"}]},
    "imm-cap": {"status": "repeal pending", "title": "REPUBLIC OF ZAMBIA THE IMMIGRATION AND DEPORTATION ACT"},
}
SECTIONS = {OLD: {"title": "", "parts": {}, "sections": {
    "24": {"current": "repealed", "history": [AMENDER]},
    "20": {"current": "amended", "history": [{**AMENDER, "op": "amended"}]},
}}}


class Base(unittest.TestCase):
    def setUp(self):
        for p in (patch.object(law_map, "_entries", lambda: ENTRIES),
                  patch.object(law_map, "_sections", lambda: SECTIONS)):
            p.start()
            self.addCleanup(p.stop)


class Notes(Base):
    def test_a_passed_act_is_not_presented_as_law(self):
        note = law_map.status_note(NEW)
        self.assertTrue(note.startswith("NOT SHOWN TO BE IN FORCE"))
        self.assertIn("Immigration and Deportation", note)
        self.assertIn("remains the law", note)

    def test_the_reader_gets_badge_fields(self):
        rows = [{"document_id": NEW, "section": "5"}, {"document_id": OLD, "section": "24"},
                {"document_id": OLD, "section": "20"}, {"document_id": OLD, "section": "7"}]
        law_map.annotate(rows)
        self.assertEqual(rows[0]["law_status"], "not in force")
        self.assertEqual((rows[1]["law_status"], rows[1]["section_state"]), ("repeal pending", "repealed"))
        self.assertEqual(rows[2]["section_state"], "amended")
        self.assertNotIn("section_state", rows[3])

    def test_dead_and_uncommenced_helpers(self):
        self.assertTrue(law_map.is_dead_section(OLD, "s. 24(1)"))
        self.assertFalse(law_map.is_dead_section(OLD, "20"))
        self.assertTrue(law_map.has_uncommenced([{"document_id": NEW}]))

    def test_the_prompt_lists_it_once_with_what_still_applies(self):
        d = law_map.pending_digest()
        self.assertEqual(d.count("Immigration Control Act, 2026"), 1)
        # Two editions of the old Act, named once, dated, singular verb.
        self.assertIn("Immigration and Deportation Act, 2010 still applies until it commences", d)


def chunk(cid, doc, section, sim):
    return {"id": cid, "document_id": doc, "content": f"text {cid}", "similarity": sim,
            "metadata": {"act_name": doc, "section_number": section}}


class Ranking(Base):
    """The dead section ranked first by meaning; live law must lead."""

    def search(self, candidates):
        with patch.object(tools, "get_query_embedding_ex", lambda q: {"vector": [0.0], "space": "gemini"}), \
                patch.object(tools, "search_chunks", lambda *a, **k: candidates):
            return asyncio.run(tools._search_corpus("business visitor permit", top_k=3))["result"]

    def test_a_repealed_section_goes_behind_live_law(self):
        r = self.search([chunk("dead", OLD, "24", 0.80), chunk("live", OLD, "20", 0.70),
                         chunk("new", NEW, "12", 0.65)])
        self.assertEqual([m["chunk_id"] for m in r["matches"]], ["live", "new", "dead"])
        self.assertIn("section_warning", r)
        self.assertIn("commencement_warning", r)
        # The warnings come before the passages they are about.
        keys = list(r)
        self.assertLess(keys.index("commencement_warning"), keys.index("matches"))

    def test_the_law_in_force_keeps_two_slots(self):
        cands = [chunk(f"new{i}", NEW, str(i), 0.9 - i / 100) for i in range(8)] + \
                [chunk("old1", OLD, "12", 0.5), chunk("old2", OLD, "28", 0.49)]
        r = self.search(cands)
        self.assertEqual([m["chunk_id"] for m in r["matches"]], ["new0", "old1", "old2"])

    def test_a_question_about_the_new_act_alone_is_not_starved(self):
        r = self.search([chunk(f"new{i}", NEW, str(i), 0.9 - i / 100) for i in range(5)])
        self.assertEqual(len(r["matches"]), 3)

    def test_a_dead_section_alone_is_a_library_miss(self):
        r = self.search([chunk("dead", OLD, "24", 0.90)])
        self.assertTrue(r.get("library_miss"))


class Audit(Base):
    def setUp(self):
        super().setUp()
        docs = [{"id": NEW, "title": "The Immigration Control Act, 2026", "short_name": "", "document_type": "act",
                 "year": 2026, "act_number": "No. 3 of 2026"},
                {"id": "nps-2026", "title": "The National Pension Scheme Act, 2026", "short_name": "",
                 "document_type": "act", "year": 2026, "act_number": "No. 72 of 2026"},
                {"id": "nps-cap", "title": "The National Pension Scheme Act", "short_name": "",
                 "document_type": "act", "year": None, "act_number": "Cap 256"}]
        for r in docs:
            title = citation_audit._with_act(r, r["title"])
            r["_ntitle"], r["_nshort"] = citation_audit._norm(title), ""
            r["_btitle"], r["_bshort"] = citation_audit._base(title), ""
        entries = {**ENTRIES, "nps-2026": {"status": "commencement pending", "year": 2026,
                                           "title": "The National Pension Scheme Act, 2026",
                                           "will_repeal": [{"id": "nps-cap", "title": "The National Pension Scheme Act"}]},
                   "nps-cap": {"status": "repeal pending"}}
        for p in (patch.object(citation_audit, "_load_index", lambda: docs),
                  patch.object(law_map, "_entries", lambda: entries)):
            p.start()
            self.addCleanup(p.stop)

    def verdict(self, answer, act):
        return next(v for v in citation_audit.audit_answer(answer) if act in (v.get("title") or ""))

    def test_citing_the_uncommenced_act_as_law_is_flagged(self):
        v = self.verdict("Under the Immigration Control Act, 2026, a work permit is issued by the Director.",
                         "Immigration Control")
        self.assertEqual(v.get("law_status"), "not in force")
        self.assertFalse(v.get("acknowledged"))
        self.assertTrue(v.get("still_applies"))

    def test_an_answer_that_says_so_is_confirmed(self):
        v = self.verdict("The Immigration Control Act, 2026 has been passed but has not yet commenced, "
                         "so the 2010 Act still governs permits.", "Immigration Control")
        self.assertTrue(v.get("acknowledged"))

    def test_the_explanation_under_its_own_heading_counts(self):
        # The live answer of 6 Oct 2026, abridged: right in substance, and
        # the audit called it "to review".
        answer = ("**No.** A business visitor permit does not authorise employment.\n\n---\n\n"
                  "## 3. What About the New Immigration Control Act, 2026?\n\n"
                  "The **Immigration Control Act, No. 3 of 2026** has been passed by the National Assembly. "
                  "Its Section 28 similarly provides for a temporary employment permit. **However, this Act has "
                  "not been shown to be in force**, and the 2010 Act remains the law.\n\n---\n\n## Summary\n")
        self.assertTrue(self.verdict(answer, "Immigration Control").get("acknowledged"))

    def test_a_block_that_relies_on_it_is_still_flagged(self):
        answer = ("## Permits\n\nUnder the Immigration Control Act, 2026 the Director issues permits.\n\n"
                  "## Older law\n\nThe Pensions Act is not yet in force.\n")
        self.assertFalse(self.verdict(answer, "Immigration Control").get("acknowledged"))

    def test_an_undated_name_shared_with_the_law_in_force_is_not_flagged(self):
        # "National Pension Scheme Act" is also Cap. 256, which is the law.
        for v in citation_audit.audit_answer("Under the National Pension Scheme Act, employers contribute monthly."):
            self.assertNotEqual(v.get("law_status"), "not in force")


if __name__ == "__main__":
    unittest.main()
