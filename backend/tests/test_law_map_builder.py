"""Repeal clauses are split per name, and a partial repeal stays partial.

The clauses are from the library: the Food Safety Act, 2019 (as read with
spaces restored on 8 Oct 2026, a margin note spliced after "sections"), the
Statistics Act, and the National Health Services Act.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))
_path = Path(__file__).resolve().parents[2] / "scripts" / "build_law_map.py"
_spec = importlib.util.spec_from_file_location("build_law_map", _path)
blm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(blm)


class RepealClauses(unittest.TestCase):
    def test_a_margin_note_after_sections_keeps_the_repeal_partial(self):
        self.assertEqual(blm.candidate_parts("The Food and Drugs Act, 1972 and sections Act No 22 of the Public Health Act, 1972"),
                         [("Food and Drugs Act", False), ("Public Health Act", True)])

    def test_numbered_sections_are_partial(self):
        self.assertEqual(blm.candidate_parts("The Food and Drugs Act, 1972 and sections 79 and 83 of the Public Health Act, 1930")[1],
                         ("Public Health Act", True))

    def test_two_whole_acts(self):
        self.assertEqual(blm.candidate_parts("The Census and Statistics Act, 1955 and the Agricultural Statistics Act, 1964"),
                         [("Census and Statistics Act", False), ("Agricultural Statistics Act", False)])

    def test_a_part_of_an_act_is_partial(self):
        self.assertIn(("Public Health Act", True),
                      blm.candidate_parts("The Medical Services Act, 1985, Part II of the Public Health Act and item 40"))


if __name__ == "__main__":
    unittest.main()


class Commencement(unittest.TestCase):
    """Hand-confirmed commencement orders (COMMENCED) apply to the right Act only."""

    def test_the_2025_cyber_acts_are_matched(self):
        self.assertIn("SI No. 22 of 2025", blm.commencement_fact({"title": "THE CYBER SECURITY ACT, 2025"})["order"])
        self.assertIn("SI No. 23 of 2025", blm.commencement_fact({"title": "The Cyber Crimes Act, 2025"})["order"])
        self.assertIn("SI No. 23 of 2025", blm.commencement_fact({"title": "Cyber Crime Act, 2025"})["order"])

    def test_the_act_they_replaced_and_amending_acts_are_not(self):
        self.assertIsNone(blm.commencement_fact({"title": "THE CYBER SECURITY AND CYBER CRIMES ACT, 2021"}))
        self.assertIsNone(blm.commencement_fact({"title": "The Cyber Security (Amendment) Act, 2026"}))
        self.assertIsNone(blm.commencement_fact({"title": "The Immigration Control Act, 2026"}))

    def test_a_reported_commencement_is_marked_reported(self):
        fact = blm.commencement_fact({"title": "The National Pension Scheme Act, 2026"})
        self.assertTrue(fact["reported"])
        self.assertIn("SI No. 62 of 2026", fact["order"])
        self.assertIsNone(blm.commencement_fact({"title": "The National Pension Scheme Act"}))
        self.assertIsNone(blm.commencement_fact({"title": "The National Pension Scheme (Amendment) Act, 2026"}))


class ReportedNotes(unittest.TestCase):
    """A reported commencement is never stated as verified, in either Act's note."""

    def test_both_notes_carry_the_caveat(self):
        from unittest.mock import patch
        from app.services import law_map
        entries = {
            "new": {"status": "in force", "title": "The National Pension Scheme Act, 2026",
                    "commenced": {"order": "SI No. 62 of 2026, whose text has not been located", "date": "early July 2026",
                                  "source": "NAPSA", "reported": True}},
            "old": {"status": "repealed", "title": "The National Pension Scheme Act",
                    "repealed_by": [{"title": "The National Pension Scheme Act, 2026", "id": "new", "reported": True}]},
        }
        with patch.object(law_map, "_entries", return_value=entries), patch.object(law_map, "_ledger", return_value=(None, False, False)):
            self.assertTrue(law_map.status_note("new").startswith("REPORTED IN FORCE"))
            old = law_map.status_note("old")
            self.assertTrue(old.startswith("REPLACED ON A REPORTED COMMENCEMENT"))
            self.assertIn("not been verified", old)
