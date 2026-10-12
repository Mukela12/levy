"""The drafting precedents (app/data/precedents.json) and the tool that serves them."""
import asyncio
import json
import sys
import types
import unittest
from pathlib import Path

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services.tools import build_tool_registry, truncate_for_model  # noqa: E402

LIBRARY = json.loads((Path(__file__).resolve().parent.parent / "app" / "data" / "precedents.json").read_text())


class Library(unittest.TestCase):
    def test_every_point_has_a_basis_and_evidence(self):
        for kind, p in LIBRARY.items():
            self.assertTrue(p["questions"] and len(p["questions"]) <= 6, kind)
            self.assertGreaterEqual(len(p["outline"]), 12, kind)
            for z in p["zambian_points"]:
                self.assertTrue(z["point"] and z["basis"] and z["evidence"], (kind, z.get("basis")))
                self.assertLessEqual(len(z["evidence"]), 200, (kind, z["basis"]))

    def test_no_em_dashes(self):
        text = json.dumps(LIBRARY, ensure_ascii=False)
        self.assertNotIn("—", text)
        self.assertNotIn("–", text)

    def test_the_consultancy_arbitration_clause_fixes_seat_and_tribunal(self):
        clause = LIBRARY["consultancy"]["clauses"]["dispute_resolution"]
        self.assertIn("Act No. 19 of 2000", clause)
        self.assertIn("Lusaka, Zambia", clause)


class Tool(unittest.TestCase):
    def setUp(self):
        self.handler = build_tool_registry(web_enabled=False)["get_drafting_precedent"].handler

    def test_aliases_reach_the_right_precedent(self):
        for asked, kind in (("Consultancy Agreement", "consultancy"), ("non-disclosure agreement", "nda"),
                            ("contract for services", "service_agreement")):
            self.assertEqual(asyncio.run(self.handler(kind=asked))["result"]["kind"], kind)

    def test_an_unknown_kind_lists_what_exists(self):
        out = asyncio.run(self.handler(kind="lease"))["result"]["error"]
        self.assertIn("consultancy", out)

    def test_nothing_is_cut_off_on_the_way_to_the_model(self):
        for kind in LIBRARY:
            text = truncate_for_model(asyncio.run(self.handler(kind=kind)), 8_000)
            self.assertNotIn("[truncated", text, kind)


if __name__ == "__main__":
    unittest.main()
