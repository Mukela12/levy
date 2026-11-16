"""The family-law and safety guides Levy holds (scripts/ingest_matter_roadmaps.py)
and the prompt rules that point the agent at them.

Read as text, not imported: the ingest script connects to Supabase at import.
A r/Zambia reader asked, in Nov 2026, how their sister could leave a violent
husband and divorce him. The custody roadmap then still sent people to two Acts
the Children's Code Act 2022 had repealed, and there was no guide for a
protection order, a divorce, or who to call.
"""
import ast
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ingest_matter_roadmaps.py"
AGENT = REPO / "backend" / "app" / "services" / "agent.py"


def _roadmaps() -> list[dict]:
    tree = ast.parse(SCRIPT.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "ROADMAPS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("ROADMAPS not found")


def _by_name() -> dict[str, dict]:
    return {g["short_name"]: g for g in _roadmaps()}


class FamilySafetyGuides(unittest.TestCase):
    def test_every_guide_title_the_prompt_names_exists(self):
        names = _by_name()
        prompt = AGENT.read_text()
        for title in ("Roadmap: protection order (gender-based violence)", "Roadmap: divorce",
                      "Getting help for gender-based violence", "Roadmap: child custody and maintenance"):
            assert title in names, title
            assert f'"{title}"' in prompt, f"agent prompt does not name {title!r}"

    def test_custody_roadmap_cites_the_childrens_code_not_the_repealed_acts(self):
        g = _by_name()["Roadmap: child custody and maintenance"]
        assert "Children's Code Act No. 12 of 2022" in g["law"]
        # The repealed Acts may be named only as repealed.
        for dead in ("Affiliation and Maintenance of Children Act", "Juveniles Act"):
            for m in re.finditer(dead, g["law"] + g["body"]):
                window = (g["law"] + g["body"])[max(0, m.start() - 200): m.end() + 40]
                assert "repealed" in window, f"{dead} cited as live law"

    def test_protection_order_guide_carries_the_core_sections(self):
        body = _by_name()["Roadmap: protection order (gender-based violence)"]["body"]
        for cite in ("s.6(3)", "s.7", "s.10(3)", "s.12", "s.20", "s.23(1)", "933", "999"):
            assert cite in body, cite

    def test_divorce_guide_separates_desertion_from_leaving_for_safety(self):
        body = _by_name()["Roadmap: divorce"]["body"]
        assert "s.9(1)(b)" in body and "s.9(1)(c)" in body
        assert "first year of the marriage" in body and "s.6" in body
        assert "Order XXXI r.4(4)" in body  # matrimonial applications go to mediation

    def test_no_em_dashes_in_levy_wording(self):
        for g in _roadmaps():
            for field in ("title", "law", "body"):
                assert "—" not in g[field], (g["short_name"], field)


if __name__ == "__main__":
    unittest.main()
