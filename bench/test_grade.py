"""The grader's own rules, on the answers that shaped them.

    python -m unittest bench/test_grade.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grade  # noqa: E402

Q = grade.QUESTIONS


class Provisions(unittest.TestCase):
    def test_the_section_must_sit_near_its_act(self):
        auth, prov = ["employment code"], [r"(?:section|s\.)\s*77\b"]
        self.assertTrue(grade.provision_cited("Under section 77 of the Employment Code Act a meal break...", auth, prov))
        self.assertTrue(grade.provision_cited("[Employment Code Act No. 3 of 2019, Section 77]", auth, prov))
        far = "The Employment Code Act governs this." + " filler" * 60 + " Section 77 of some other Act."
        self.assertFalse(grade.provision_cited(far, auth, prov))


class DeadLaw(unittest.TestCase):
    def grade(self, qid, text):
        return grade.score_answer(Q[qid], text)

    def test_applying_a_repealed_section_is_a_hallucination(self):
        r = self.grade("business-permit", "No. Under section 24 of the Immigration and Deportation Act a business "
                                          "permit is valid for 30 days and does not authorise employment.")
        self.assertEqual(r["grade"], "hallucinated")

    def test_naming_it_as_repealed_is_fine(self):
        r = self.grade("business-permit", "No, it does not authorise employment under the Immigration and Deportation "
                                          "Act. Section 24 of that Act was repealed in 2016.")
        self.assertEqual(r["grade"], "correct")

    def test_a_subsection_heading_belongs_to_its_parent(self):
        text = ("The Juveniles Act was repealed by the Children's Code Act, 2022.\n\n"
                "## What the old Juveniles Act said (historical)\n\n### Section 73\n\nA court could dismiss the charge.\n")
        self.assertEqual(self.grade("juveniles-repeal", text)["grade"], "correct")


class Premise(unittest.TestCase):
    def test_accepting_a_false_premise(self):
        r = grade.score_answer(Q["fp-maternity-12-weeks"], "Under the Employment Code, section 41, your employer can "
                                                            "refuse a 13th week since the leave is 12 weeks.")
        self.assertEqual(r["grade"], "hallucinated")
        r = grade.score_answer(Q["fp-maternity-12-weeks"], "Section 41 of the Employment Code gives fourteen weeks, "
                                                            "not 12, so a 13th week is yours.")
        self.assertEqual(r["grade"], "correct")


class Interval(unittest.TestCase):
    def test_ten_questions_decide_little(self):
        lo, hi = grade.wilson(8, 10)
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.9)


if __name__ == "__main__":
    unittest.main()
