"""Quotations are checked against the section or judgment they are attributed to.

The section texts below are copied from the library's Employment Code, OCR
squashing and margin notes included, so the checks run without a database.
"""
import sys
import types
import unittest

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services import quote_check as qc  # noqa: E402

S74 = ("EMPLOYMENT CODE ACT - Part IV - Section 74. Hours of work 74. (1)Thenormaldays’ workofafull-timeemployee— "
       "(a)shallconsistofeighthoursofactualwork;and (b) may begin on any day of the week. (2) An employer and an "
       "employee, other than a part-time employee, may agree that the employee works in excess of the "
       "stipulatedhourswithoutaddedremunerationifthenumberofhours covered in a week does not exceed forty-eight hours")
S75 = ("EMPLOYMENT CODE ACT - Part IV - Section 75. Overtime 75. (1) Subject to subsection (2), an employer shall pay an "
       "Overtime 75. (1) Subject to subsection (2), an employer shall pay an employeewhoworksinexcessofforty-eighthoursinaweek,"
       "one andhalftimestheemployee’shourlyrateofpay. (4) Anemployershall,incalculatingthehourlyrateofpayin a month, "
       "divide the actual amount received by the employee in basic wagesforthat month— (a)bytwohundredandeighthoursfor"
       "afull-timeemployee, other thana watchperson or guard;and (b)bytwohundredandfortyhoursforafull-timewatchperson orguard.")
AMENDMENT = "Section 75 of the principal Act is amended by the insertion of the words an employer shall pay a night premium of ten percent for each hour"
SECTIONS = {"74": S74, "75": S75}


def fetch_sections(doc_id, sections):
    return tuple((s, SECTIONS[s]) for s in sections if s in SECTIONS)


def fetch_document(doc_id):
    return AMENDMENT if doc_id == "amend" else ""


def amending(doc_id):
    return [{"id": "amend", "title": "Employment Code (Amendment) Act, 2099"}]


def check(quote, section):
    return qc.check_statute_quote(quote, "ec", section, fetch_sections=fetch_sections,
                                  fetch_document=fetch_document, amending=amending)


class Matching(unittest.TestCase):
    def test_a_true_quotation_matches_through_ocr_squashing(self):
        q = ("An employer shall, in calculating the hourly rate of pay in a month, divide the actual amount received "
             "by the employee in basic wages for that month by two hundred and eight hours for a full-time employee")
        self.assertIn(check(q, "75")["status"], ("verbatim", "close"))

    def test_ellipses_split_the_quotation(self):
        q = "an employee who works in excess of forty-eight hours in a week ... one and half times the employee's hourly rate of pay"
        self.assertEqual(check(q, "75")["status"], "verbatim")

    def test_the_208_hour_myth_in_quotation_marks_is_not_found(self):
        q = "An employer is only required to pay overtime once the employee has worked more than two hundred and eight hours in a month"
        self.assertEqual(check(q, "75")["status"], "not_found")

    def test_words_from_the_next_section_are_placed(self):
        q = ("An employer and an employee, other than a part-time employee, may agree that the employee works in "
             "excess of the stipulated hours without added remuneration")
        self.assertEqual(check(q, "75"), {"status": "elsewhere", "found_in": "74"})

    def test_wording_from_an_amending_act_is_recognised(self):
        q = "an employer shall pay a night premium of ten percent for each hour"
        self.assertEqual(check(q, "75")["status"], "amended")

    def test_a_section_the_library_lacks_is_left_unchecked(self):
        self.assertEqual(check("an employer must give every employee a paid birthday leave day each year", "99")["status"],
                         "unchecked")


class Attribution(unittest.TestCase):
    def cites(self, text):
        name = "Employment Code Act"
        return [{"kind": "statute", "name": name, "text": name}], [{"id": "ec"}]

    def run_check(self, text):
        cites, rows = self.cites(text)
        return qc.check_quotes(text, cites, rows, fetch_sections=fetch_sections,
                               fetch_document=fetch_document, amending=amending)

    def test_the_citation_before_the_quotation_is_used(self):
        text = ('Under the Employment Code Act, section 75(4) provides: "An employer is only required to pay overtime '
                'once the employee has worked more than two hundred and eight hours in a month."\n\nSection 77 of the '
                'Employment Code Act covers meal breaks.')
        out = self.run_check(text)
        self.assertEqual(out[0][0]["section"], "75")
        self.assertEqual(out[0][0]["status"], "not_found")

    def test_levys_bracket_style_after_a_blockquote(self):
        text = ("The rule:\n\n> An employer and an employee, other than a part-time employee, may agree that the "
                "employee works in excess of the stipulated hours without added remuneration\n\n"
                "[Employment Code Act No. 3 of 2019, Section 74]")
        out = self.run_check(text)
        self.assertEqual(out[0][0]["section"], "74")
        self.assertIn(out[0][0]["status"], ("verbatim", "close"))

    def test_short_quotations_are_ignored(self):
        self.assertEqual(self.run_check('The Employment Code Act, section 75, calls it "overtime".'), {})

    def test_an_unattributed_quotation_is_ignored(self):
        cites, rows = self.cites("")
        text = 'As the saying goes, "justice delayed is justice denied and every litigant knows it well".'
        self.assertEqual(qc.check_quotes(text, cites, rows, fetch_sections=fetch_sections), {})


if __name__ == "__main__":
    unittest.main()


class Guards(unittest.TestCase):
    def test_a_section_number_shared_with_bundled_court_rules_is_not_judged(self):
        mixed = lambda doc_id, sections: (("27", "IV", "27. Power of courts to transfer cases"),
                                          ("27", "XI", "27. Where a debtor against whom a composition order has been made "
                                                       "changes his address, he shall at once give notice to the clerk of the court."))
        q = "No proceedings which may have been taken previously to such plea in objection shall be in any way affected"
        self.assertEqual(qc.check_statute_quote(q, "sca", "27", fetch_sections=mixed, fetch_document=lambda d: "",
                                                amending=lambda d: [])["status"], "unchecked")
