"""What the model and the reader are told about a single section.

Built around the case that started it: section 24 of the Immigration and
Deportation Act 2010, repealed by section 9 of Act No. 19 of 2016, while the
Act itself stays in force until the Immigration Control Act 2026 commences.
"""
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services import citation_audit, law_map

ACT = "act-2010"
AMENDER = {"by_id": "amend-2016", "by_title": "The Immigration and Deportation (Amendment)",
           "by_number": "No. 19 of 2016", "by_year": 2016, "confidence": "high",
           "evidence": "The principal Act is amended by the repeal of section twenty-four."}
SECTIONS = {ACT: {"title": "The Immigration and Deportation 2010", "parts": {}, "sections": {
    "24": {"current": "repealed", "history": [{"op": "repealed", **AMENDER}]},
    "20": {"current": "amended", "history": [{"op": "amended", **AMENDER}]},
    "77": {"current": "replaced", "history": [{"op": "replaced", **AMENDER}]},
    "83": {"current": "repealed", "history": [{"op": "repealed", **{**AMENDER, "confidence": "medium"}}]},
    "32": {"current": "uncertain", "history": [{"op": "repealed", **AMENDER}, {"op": "amended", **AMENDER}]},
}}}
ENTRIES = {ACT: {"status": "repeal pending", "title": "The Immigration and Deportation 2010", "year": 2010,
                 "repeal_pending_by": [{"id": "ica-2026", "title": "The Immigration Control Act, 2026"}],
                 "amended_by": [{"id": "amend-2016", "title": "The Immigration and Deportation (Amendment)"}]},
           "ica-2026": {"status": "in force", "title": "The Immigration Control Act, 2026", "year": 2026},
           "amend-2016": {"status": "amending Act", "title": "The Immigration and Deportation (Amendment)",
                          "year": 2016}}


class Base(unittest.TestCase):
    def setUp(self):
        for p in (patch.object(law_map, "_sections", lambda: SECTIONS),
                  patch.object(law_map, "_entries", lambda: ENTRIES)):
            p.start()
            self.addCleanup(p.stop)


class SectionNotes(Base):
    def test_a_repealed_section_of_a_live_act(self):
        rows = [{"document_id": ACT, "section": "24"}]
        law_map.annotate(rows)
        self.assertIn("COMMENCEMENT NOT VERIFIED", rows[0]["status"])
        self.assertIn("not evidence", rows[0]["status"])
        self.assertNotIn("STILL IN FORCE", rows[0]["status"])
        self.assertTrue(rows[0]["section_status"].startswith("SECTION 24 IS REPEALED"))
        self.assertIn("No. 19 of 2016", rows[0]["section_status"])

    def test_the_act_note_now_mentions_its_amendments(self):
        # This branch used to stop at "still in force", which is how
        # section 24 went unmentioned.
        self.assertIn("amended by", law_map.status_note(ACT))

    def test_replaced_says_where_the_current_wording_is(self):
        note = law_map.section_note(ACT, "77")
        self.assertIn("REPEALED AND REPLACED", note)
        self.assertNotIn("IS REPEALED", note)

    def test_a_medium_confidence_repeal_is_hedged(self):
        self.assertIn("confirm it there", law_map.section_note(ACT, "83"))
        self.assertNotIn("confirm it there", law_map.section_note(ACT, "24"))

    def test_a_contradiction_is_not_resolved_by_guessing(self):
        self.assertIn("cannot both be right", law_map.section_note(ACT, "32"))

    def test_an_untouched_section_gets_no_note(self):
        rows = [{"document_id": ACT, "section": "27"}]
        law_map.annotate(rows)
        self.assertNotIn("section_status", rows[0])

    def test_section_written_any_way(self):
        for form in ("24", "s. 24", "section 24(1)(b)", "Section twenty-four"):
            self.assertIsNotNone(law_map.section_note(ACT, form), form)

    def test_dead_section_detection(self):
        rows = [{"document_id": ACT, "section": "24"}, {"document_id": ACT, "section": "20"}]
        law_map.annotate(rows)
        self.assertTrue(law_map.has_dead_section(rows))
        self.assertFalse(law_map.has_dead_section(rows[1:]))


class ProvisionReport(Base):
    def test_a_section_query(self):
        rep = law_map.provision_report(ACT, "24")
        self.assertEqual(rep["act_status"], "repeal pending")
        self.assertEqual(rep["section"]["current"], "repealed")
        self.assertEqual(rep["section"]["history"][0]["year"], 2016)

    def test_nothing_recorded_is_not_a_guarantee(self):
        rep = law_map.provision_report(ACT, "27")
        self.assertEqual(rep["section"]["current"], "no change recorded")
        self.assertIn("not proof", rep["section"]["note"])

    def test_a_whole_act_query_lists_what_is_dead(self):
        rep = law_map.provision_report(ACT)
        self.assertEqual(rep["repealed_sections"], ["24", "83"])
        self.assertEqual(rep["replaced_sections"], ["77"])


class Audit(Base):
    ROW = {"id": ACT}

    def test_finds_the_section_either_side_of_the_act(self):
        a = "Under section 24 of the Immigration and Deportation Act 2010, a permit is issued."
        self.assertEqual(citation_audit._cited_sections(a, "Immigration and Deportation Act 2010"), ["24"])
        b = "[Immigration and Deportation Act 2010, Section 24] (Page 25)"
        self.assertEqual(citation_audit._cited_sections(b, "Immigration and Deportation Act 2010"), ["24"])

    def test_the_benchmark_answer_is_flagged(self):
        a = "Under section 24 of the Immigration and Deportation Act 2010, a business permit may be issued."
        dead = citation_audit._dead_sections(a, "Immigration and Deportation Act 2010", self.ROW)
        self.assertEqual([(d["section"], d["status"], d["acknowledged"]) for d in dead], [("24", "repealed", False)])

    def test_an_answer_that_says_so_is_confirmed_not_flagged(self):
        a = ("Section 24 of the Immigration and Deportation Act 2010 once governed this, but section 24 "
             "was repealed by Act No. 19 of 2016.")
        dead = citation_audit._dead_sections(a, "Immigration and Deportation Act 2010", self.ROW)
        self.assertTrue(dead and dead[0]["acknowledged"])

    def test_an_amended_section_is_not_badged(self):
        a = "Section 20 of the Immigration and Deportation Act 2010 sets out the conditions."
        self.assertEqual(citation_audit._dead_sections(a, "Immigration and Deportation Act 2010", self.ROW), [])


if __name__ == "__main__":
    unittest.main()


class ProvisionTool(unittest.IsolatedAsyncioTestCase):
    """check_provision_status choosing among Acts that share a name."""

    def setUp(self):
        from app.services import citation_audit as ca
        self.ca = ca
        docs = [
            {"id": "co-old", "title": "REPUBLIC OF ZAMBIA THE COMPANIES ACT", "short_name": "", "document_type": "act", "year": None, "act_number": ""},
            {"id": "co-2017", "title": "THE COMPANIES ACT, 2017", "short_name": "", "document_type": "act", "year": 2017, "act_number": "No. 10 of 2017"},
            {"id": "co-amend", "title": "The Companies (Amendment) Act, 2020", "short_name": "", "document_type": "act", "year": 2020, "act_number": ""},
            {"id": "zda", "title": "The Zambia Development Agency", "short_name": "", "document_type": "act", "year": 2006, "act_number": ""},
        ]
        for r in docs:
            title = ca._with_act(r, r["title"])
            r["_ntitle"], r["_nshort"] = ca._norm(title), ""
            r["_btitle"], r["_bshort"] = ca._base(title), ""
        sections = {"co-old": {"title": "", "parts": {}, "sections": {
            "378": {"current": "repealed", "history": [{"op": "repealed", **AMENDER}]}}}}
        entries = {"co-old": {"status": "repealed", "title": "Companies Act"},
                   "co-2017": {"status": "in force", "title": "Companies Act, 2017", "year": 2017},
                   "zda": {"status": "in force", "title": "Zambia Development Agency Act", "year": 2006}}
        for p in (patch.object(ca, "_load_index", lambda: docs),
                  patch.object(law_map, "_sections", lambda: sections),
                  patch.object(law_map, "_entries", lambda: entries)):
            p.start()
            self.addCleanup(p.stop)

    async def ask(self, act, section=None):
        from app.services import tools
        return (await tools._check_provision_status(act, section))["result"]

    async def test_a_named_year_comes_first(self):
        # By name the 2017 Act is the better match; the user asked for 1994.
        r = await self.ask("Companies Act 1994", "378")
        self.assertEqual(r["matches"][0]["section"]["current"], "repealed")
        self.assertIn("answer_rule", r)

    async def test_no_year_means_the_act_in_force_first(self):
        r = await self.ask("Companies Act", "378")
        self.assertEqual(r["matches"][0]["year"], 2017)
        self.assertTrue(any(m["section"]["current"] == "repealed" for m in r["matches"]))

    async def test_amending_acts_are_not_listed_as_the_same_act(self):
        r = await self.ask("Companies Act", "378")
        self.assertFalse(any("Amendment" in (m["title_in_library"] or "") for m in r["matches"]))

    async def test_a_title_that_lost_its_act_is_still_found(self):
        r = await self.ask("Zambia Development Agency Act", "58")
        self.assertTrue(r["found"])
        self.assertEqual(r["matches"][0]["title_in_library"], "The Zambia Development Agency")

    async def test_an_act_not_held_sends_the_model_to_the_source(self):
        r = await self.ask("Imaginary Widgets Act 2031", "4")
        self.assertFalse(r["found"])
        self.assertIn("parliament.gov.zm", r["next_step"])
