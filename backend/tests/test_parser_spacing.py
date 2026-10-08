"""Pages whose words pdfplumber glues together are re-read with a tighter gap.

The strings are the two readings of real pages: the Employment Code Act 2019,
p.61, and the Judiciary Administration (Amendment) Act 2018, s.2.
"""
import sys
import types
import unittest

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services.parser import choose_page_text  # noqa: E402

GLUED = ("(b)refusetheapplicationandnotifythepermitholder,giving reasons for the refusal. 118. (1) An employee "
         "and the prospective employer shall Theprincipal Actisamendedbythedeletionofsection13 and substitution "
         "thereforofthefollowing: Anemployershall,incalculatingthehourlyrateofpayin a month, divide the amount")
SPACED = ("(b) refuse the application and notify the permit holder, giving reasons for the refusal. 118. (1) An "
          "employee and the prospective employer shall The principal Act is amended by the deletion of section 13 "
          "and substitution therefor of the following: An employer shall, in calculating the hourly rate of pay in "
          "a month, divide the amount")
CLEAN = ("1. This Act may be cited as the Lands Act. 2. In this Act, unless the context otherwise requires, "
         "land means any interest in land, whether the interest is held under customary tenure or leasehold.")


class Spacing(unittest.TestCase):
    def test_a_glued_page_takes_the_spaced_reading(self):
        self.assertEqual(choose_page_text(GLUED, SPACED), SPACED)

    def test_a_clean_page_is_left_alone(self):
        self.assertEqual(choose_page_text(CLEAN, CLEAN.replace("Lands", "L ands")), CLEAN)

    def test_a_tighter_reading_that_splits_letters_is_refused(self):
        split = " ".join(SPACED.replace("employer", "e m p l o y e r").replace("amount", "a m o u n t").split())
        self.assertEqual(choose_page_text(GLUED, split + " p r i n c i p a l"), GLUED)

    def test_an_empty_tight_reading_keeps_the_default(self):
        self.assertEqual(choose_page_text(GLUED, ""), GLUED)


if __name__ == "__main__":
    unittest.main()
