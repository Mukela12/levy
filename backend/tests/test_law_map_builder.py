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
