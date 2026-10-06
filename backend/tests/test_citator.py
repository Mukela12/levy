"""The citator: what the judgments in the library say about the cases they cite.

These run against the committed app/data/citator.json, built by
scripts/build_citator.py from the 1,165 judgments in the library.
"""
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services import citation_audit as ca  # noqa: E402
from app.services import citator as ct  # noqa: E402


class Names(unittest.TestCase):
    def test_footnote_markers_and_neighbouring_text_are_cut(self):
        self.assertEqual(ct.clean_party("Attorney General® and Chikuta", "a"), "Chikuta")
        self.assertEqual(ct.clean_party("The People® and Saidi Banda", "b"), "The People")
        self.assertEqual(ct.clean_party("J8 Yokoniya Mwale", "a"), "Yokoniya Mwale")
        self.assertEqual(ct.clean_party("The People4", "b"), "The People")

    def test_report_citations(self):
        self.assertEqual(ct.report_cites("(1982) Z.R. 172 (S.C.)")[0], ["(1982) ZR 172"])
        self.assertEqual(ct.report_cites("[2019] ZMSC 5")[0], ["[2019] ZMSC 5"])
        self.assertEqual(ct.report_cites("SCZ Judgment No. 8 of 2006")[0], ["SCZ Judgment No. 8 of 2006"])


class Lookup(unittest.TestCase):
    def test_a_leading_case_levy_does_not_hold_is_known(self):
        hit = ct.lookup("Wilson Masauso Zulu", "Avondale Housing Project Limited", "(1982) ZR 172")
        self.assertIsNotNone(hit)
        self.assertFalse(hit["year_conflict"])
        self.assertGreater(hit["case"]["n"], 100)
        self.assertIn("(1982) ZR 172", hit["case"]["cites"])
        self.assertIsNone(hit["case"]["doc"])

    def test_a_short_form_finds_it(self):
        self.assertEqual(ct.lookup("Zulu", "Avondale Housing Project")["case"]["cites"][0], "(1982) ZR 172")

    def test_a_wrong_year_is_a_conflict(self):
        self.assertTrue(ct.lookup("Wilson Masauso Zulu", "Avondale Housing Project", "(1983) ZR 172")["year_conflict"])

    def test_the_audits_own_fabrication_example_stays_unknown(self):
        # "Zulu v The People (1990-2) ZR 65": many Zulus, and no judgment cites that year.
        self.assertIsNone(ct.lookup("Zulu", "The People", "(1990-2) ZR 65"))
        self.assertIsNone(ct.lookup("Zulu", "The People", ""))

    def test_an_invented_case_is_unknown(self):
        self.assertIsNone(ct.lookup("Kalusha Bwalya", "Chilufya Mwansa", "(2005) ZR 12"))

    def test_reviewed_treatment(self):
        zubao = ct.lookup("Zubao Harry Juma", "First Quantum Mining & Operations Ltd")["case"]
        self.assertEqual([n["kind"] for n in zubao["neg"]], ["departed from"])
        self.assertIn("section 54(1)(c)", zubao["neg"][0]["extent"])
        guardall = ct.lookup("Guardall Security Group Limited", "Reinford Kabwe")["case"]
        self.assertEqual(guardall["neg"][0]["kind"], "reversed")

    def test_a_different_case_with_a_shared_party_is_not_tarred(self):
        # Legal Resources Foundation v Attorney General (2025) is not the per incuriam decision.
        hit = ct.lookup("Legal Resources Foundation Limited", "The Attorney General", "2025/CCZ/0020")
        self.assertTrue(hit is None or not hit["case"].get("neg"))

    def test_describe_gives_how_courts_use_it(self):
        d = ct.describe(ct.lookup("Khalid Mohamed", "The Attorney General")["case"], limit=3)
        self.assertEqual(d["citations"][0], "(1982) ZR 49")
        self.assertTrue(d["cited_in"] and all(x["judgment"] and x["excerpt"] for x in d["cited_in"]))


class Audit(unittest.TestCase):
    """The audit carries what the citator knows into each case verdict."""

    def setUp(self):
        ca._INDEX = []
        ca._INDEX_AT = 1e18
        self.addCleanup(setattr, ca, "_INDEX", None)

    def test_unheld_case_is_known_and_a_wrong_year_is_flagged(self):
        with patch("app.services.quote_check.check_quotes", lambda *a, **k: {}):
            out = ca.audit_answer("See Wilson Masauso Zulu v Avondale Housing Project Limited (1983) ZR 172 on findings of fact.")
        v = out[0]
        self.assertEqual(v["status"], "not_found")
        self.assertEqual(v["known"]["citation"], "(1982) ZR 172")
        self.assertTrue(v["known"]["year_conflict"])

    def test_departure_is_attached_unless_the_answer_says_so(self):
        with patch("app.services.quote_check.check_quotes", lambda *a, **k: {}):
            plain = ca.audit_answer("In Zubao Harry Juma v First Quantum Mining & Operations Ltd permanent employees got severance.")
            said = ca.audit_answer("Zubao Harry Juma v First Quantum Mining & Operations Ltd was departed from in Kingfred Phiri.")
        self.assertEqual(plain[0]["treatment"][0]["treatment"], "departed from")
        self.assertNotIn("treatment_acknowledged", plain[0])
        self.assertTrue(said[0]["treatment_acknowledged"])


if __name__ == "__main__":
    unittest.main()
