"""A formal document is set the way Zambian courts and advocates set one.

The first live court papers and agreement (17 Nov 2026) were sound in their
words and wrong on the page: a statement of claim printed as a memo with the
court's name run into one line, an affidavit headed APPLICANT over a body
that said Plaintiff, the parties in ordinary type, signature lines four
underscores long, clause numbers flush against their text, and the whole of
Order 27 rule 4 quoted in the middle of a sentence. The layout these tests
hold to was read off judgments of the Supreme Court, Court of Appeal,
Constitutional Court and High Court and off the forms in their rules.
"""
import io
import re
import sys
import types
import unittest
from unittest.mock import patch

import markdown

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services import doc_design as d, doc_typeset as ts, docx_tools, pdf_tools, tools  # noqa: E402


def set_(body_md: str, layout: str, title_hint: str = "") -> str:
    html = markdown.markdown(d.tidy_source(body_md), extensions=d.markdown_extensions(layout))
    return d.normalise(html, layout, title_hint)


def words(html: str) -> str:
    """The words of a page, without its marks, rules or quotation marks."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"[\"'‘’“”_.…]", "", text.replace("&amp;", "&").replace("\xa0", " "))
    return re.sub(r"\s+", " ", text).strip()


TYPED_HEADING = """**IN THE HIGH COURT FOR ZAMBIA**
**AT THE COMMERCIAL REGISTRY**
**HOLDEN AT LUSAKA**
**(Civil Jurisdiction)**

**Cause No. 2026/HPC/0412**

**BETWEEN:**

**MWILA HARDWARE LIMITED** ........................................ **PLAINTIFF**

**AND**

**TEMBO CONSTRUCTION LIMITED** ................................ **1ST DEFENDANT**

**PETER TEMBO** ........................................................ **2ND DEFENDANT**

---

## THE PARTIES

1. The Plaintiff is a limited liability company.
"""


class Heading(unittest.TestCase):
    def test_the_heading_of_an_action_is_set_as_the_courts_set_it(self):
        html = pdf_tools.render_court_heading(
            court_division="Principal Registry, Civil", cause_number="2026/HP/1482",
            applicant_name="Chanda Mulenga", respondent_name="Kafue Estates Limited",
            applicant_role="PLAINTIFF", respondent_role="DEFENDANT")
        # the court at the left, the number alone opposite it (no "Cause No."), which
        # leaves the middle of the page clear for the registry's date stamp
        self.assertIn('<td class="court"><div>IN THE HIGH COURT FOR ZAMBIA</div><div>AT THE PRINCIPAL REGISTRY</div>'
                      '<div>HOLDEN AT LUSAKA</div><div class="jurisdiction">(Civil Jurisdiction)</div></td>'
                      '<td class="cause">2026/HP/1482</td>', html)
        self.assertIn('<p class="between">BETWEEN:</p>', html)
        self.assertIn('<td class="party"><strong>CHANDA MULENGA</strong></td><td class="role">PLAINTIFF</td>', html)
        self.assertIn('<td class="and" colspan="2">AND</td>', html)
        self.assertIn('<strong>KAFUE ESTATES LIMITED</strong></td><td class="role">DEFENDANT</td>', html)

    def test_several_parties_are_numbered_and_a_capacity_sits_under_the_name(self):
        html = pdf_tools.render_court_heading(
            court_division="Constitutional Court", cause_number=None,
            applicant_name="Mary Banda (suing as administratrix of the estate of the late John Banda); Dunavant (Z) Limited",
            respondent_name="The Attorney General", applicant_role="PETITIONER", respondent_role="RESPONDENT")
        self.assertIn("IN THE CONSTITUTIONAL COURT OF ZAMBIA", html)
        self.assertIn('<strong>MARY BANDA</strong><br><em class="capacity">(suing as administratrix of the estate of '
                      'the late John Banda)</em></td><td class="role">1ST PETITIONER</td>', html)
        # "(Z)" is part of a company's name, not a capacity
        self.assertIn('<strong>DUNAVANT (Z) LIMITED</strong></td><td class="role">2ND PETITIONER</td>', html)
        self.assertIn("/CCZ/[NUMBER]", html)

    def test_each_court_is_named_in_its_own_words(self):
        self.assertEqual(pdf_tools.court_lines("Principal Registry, Commercial")[0][1], "AT THE COMMERCIAL REGISTRY")
        self.assertEqual(pdf_tools.court_lines("Kitwe District Registry"),
                         (["IN THE HIGH COURT FOR ZAMBIA", "AT THE DISTRICT REGISTRY", "HOLDEN AT KITWE",
                           "(Civil Jurisdiction)"], "{year}/HK/[NUMBER]"))
        self.assertEqual(pdf_tools.court_lines("Subordinate Court at Ndola")[0][:2],
                         ["IN THE SUBORDINATE COURT OF THE FIRST CLASS", "FOR THE NDOLA DISTRICT"])
        self.assertEqual(pdf_tools.court_lines("Court of Appeal")[0][0], "IN THE COURT OF APPEAL OF ZAMBIA")
        self.assertIn("(Divorce Jurisdiction)", pdf_tools.court_lines("Family Division, divorce petition")[0])

    def test_a_heading_the_model_typed_out_becomes_the_real_thing(self):
        out = set_(TYPED_HEADING, "court", title_hint="STATEMENT OF CLAIM")
        self.assertIn('<td class="cause">2026/HPC/0412</td>', out)
        self.assertEqual(out.count('<td class="party">'), 3)
        self.assertIn('<strong>TEMBO CONSTRUCTION LIMITED</strong></td><td class="role">1ST DEFENDANT</td>', out)
        self.assertNotIn("....", out)                       # the dots that pushed each title to the right are gone
        # named by the tool it came through, not after its first section heading
        self.assertIn('<div class="doc-title">STATEMENT OF CLAIM</div>', out)
        self.assertRegex(out, r"<h2[^>]*>THE PARTIES</h2>")
        self.assertIn("The Plaintiff is a limited liability company.", out)

    def test_the_other_ways_a_heading_has_been_typed(self):
        as_headings = ("# IN THE HIGH COURT FOR ZAMBIA\n## AT THE PRINCIPAL REGISTRY\n### HOLDEN AT LUSAKA\n"
                       "#### (Civil Jurisdiction)\n\n**CAUSE NO. 2025/HP/[NUMBER]**\n\n---\n\n**BETWEEN:**\n\n"
                       "**JOHN PHIRI** (suing as father and next friend of MARY PHIRI, a minor)\n**...PLAINTIFF**\n\n"
                       "**AND**\n\n**LUSAKA CITY COUNCIL**\n**...DEFENDANT**\n\n---\n\n# STATEMENT OF CLAIM\n\n---\n\n"
                       "1. The Plaintiff is a teacher.\n")
        out = set_(as_headings, "court")
        self.assertIn('<td class="cause">2025/HP/[NUMBER]</td>', out)
        self.assertIn('<strong>JOHN PHIRI</strong><br><em class="capacity">(suing as father and next friend of MARY '
                      'PHIRI, a minor)</em></td><td class="role">PLAINTIFF</td>', out)
        self.assertIn('<div class="doc-title">STATEMENT OF CLAIM</div>', out)
        self.assertNotIn("<hr", out)                        # the title is ruled off by its own two rules
        as_table = ("## IN THE HIGH COURT FOR ZAMBIA\n## INDUSTRIAL RELATIONS DIVISION\n## HOLDEN AT NDOLA\n\n"
                    "**COMP NO. IRCND/43/2025**\n\nBETWEEN:\n\n| | |\n|---|---|\n| MARY BANDA | 1ST COMPLAINANT |\n"
                    "| JOHN ZULU | 2ND COMPLAINANT |\n| **AND** | |\n| KONKOLA MINES PLC | **RESPONDENT** |\n\n"
                    "## NOTICE OF COMPLAINT\n\nThe complainants say:\n")
        out = set_(as_table, "court")
        self.assertIn('<td class="cause">COMP NO IRCND/43/2025</td>', out.replace("NO.", "NO"))
        self.assertEqual(out.count('<td class="party">'), 3)
        self.assertIn('<td class="role">2ND COMPLAINANT</td>', out)
        self.assertIn('<div class="doc-title">NOTICE OF COMPLAINT</div>', out)

    def test_a_cause_number_not_yet_known_does_not_stop_the_heading_being_read(self):
        # the heading exactly as the prompt asks for it, as the first live draft wrote it
        for number in ("[CAUSE NUMBER]", "2026/HP/[NUMBER]", "[YEAR]/HPC/[NUMBER]", "CAZ/08/35/2018", "2026/HP/........"):
            body = ("IN THE HIGH COURT FOR ZAMBIA\nAT THE PRINCIPAL REGISTRY\nHOLDEN AT LUSAKA\n(Civil Jurisdiction)\n\n"
                    f"{number}\n\nBETWEEN:\n\nMWILA HARDWARE LIMITED ........ PLAINTIFF\n\nAND\n\n"
                    "TEMBO CONSTRUCTION LIMITED ........ 1ST DEFENDANT\n\nPETER TEMBO ........ 2ND DEFENDANT\n\n"
                    "## STATEMENT OF CLAIM\n\n**The parties**\n\n1. The Plaintiff is a company.\n")
            out = set_(body, "court")
            self.assertIn('<table class="caption">', out, number)
            self.assertEqual(out.count('<td class="party">'), 3, number)
            self.assertIn('<div class="doc-title">STATEMENT OF CLAIM</div>', out, number)
        self.assertIn('<td class="cause">2026/HP/<span class="rule dots"', out)      # the last one: dots to write the number on

    def test_what_is_not_a_heading_is_left_alone(self):
        memo = "# Which court\n\nThe claim belongs IN THE HIGH COURT FOR ZAMBIA, not the Subordinate Court.\n\nBETWEEN the two, cost decides."
        self.assertNotIn("caption", set_(memo, "court"))
        # a heading with one party only cannot be laid out: nothing is lost
        one = "**IN THE HIGH COURT FOR ZAMBIA**\n\n**BETWEEN:**\n\n**JOHN PHIRI** ..... **PLAINTIFF**\n\nText."
        self.assertNotIn('class="caption"', set_(one, "court"))
        self.assertIn("JOHN PHIRI", set_(one, "court"))

    def test_a_heading_stored_before_the_change_prints_like_a_new_one(self):
        old = ('<div class="court-caption"><div class="line">IN THE HIGH COURT FOR ZAMBIA</div><div class="line">AT THE '
               'PRINCIPAL REGISTRY</div><div class="line">HOLDEN AT LUSAKA</div><div class="jurisdiction">(Civil '
               'Jurisdiction)</div></div><div class="cause-number">Cause No. 2026/HP/1482</div><div class="between">'
               'B E T W E E N:</div><table class="parties"><tr><td>Chanda Mulenga</td><td class="right">APPLICANT</td>'
               '</tr><tr><td>AND</td><td></td></tr><tr><td>Kafue Estates Limited</td><td class="right">RESPONDENT</td>'
               '</tr></table>\n\n<div class="doc-title">AFFIDAVIT IN SUPPORT</div>\n\n'
               '<h2 style="text-align:left;font-size:12pt;">1.0 INTRODUCTION</h2><p><strong>1.1</strong> These are.</p>')
        out = d.normalise(old, "court")
        self.assertIn('<td class="cause">2026/HP/1482</td>', out)
        self.assertIn("<strong>CHANDA MULENGA</strong>", out)
        self.assertNotIn("court-caption", out)
        self.assertNotIn("B E T W E E N", out)
        self.assertNotIn("font-size:12pt", out)             # sizes belong to the stylesheet

    def test_a_formal_document_sent_to_the_memo_tool_is_recognised(self):
        self.assertEqual(d.formal_layout_of(TYPED_HEADING), "court")
        self.assertEqual(d.formal_layout_of("12 May 2026\n\nDear Mr Phiri,\n\nPay.\n\nYours faithfully,\n\nM. Banda"), "letter")
        self.assertEqual(d.formal_layout_of("**THIS TENANCY AGREEMENT** is made on the 20th day of November 2026"), "agreement")
        self.assertIsNone(d.formal_layout_of("# Litigation roadmap\n\nFile in the High Court. Dear reader, note the costs."))
        self.assertIsNone(d.formal_layout_of("## Advice\n\nThe letter should close 'Yours faithfully'."))


class Clauses(unittest.TestCase):
    AGREEMENT = ("# TENANCY AGREEMENT\n\n**(1) MUTALE PROPERTIES LIMITED**, a company (\"the Landlord\");\n\n"
                 "A. The Landlord owns the house.\n\n## 1. DEFINITIONS\n\n1.1 In this Agreement:\n\n"
                 "(a) **\"the Premises\"** means the house;\n\n(i) with its garden;\n\n(b) \"the Term\" means a year.\n\n"
                 "1.2 Headings do not affect interpretation.\n\n## 10. RENEWAL\n\n10.12 The Tenant may renew.\n")

    def test_each_number_stands_in_its_own_column_and_each_level_sits_under_the_last(self):
        out = set_(self.AGREEMENT, "agreement")
        num = re.search(r'<p class="cl" style="margin-left:0.00em;padding-left:([\d.]+)em;text-indent:-\1em">'
                        r'<span class="n" style="width:\1em">1\.1</span>In this Agreement:</p>', out)
        self.assertIsNotNone(num, out)
        col = float(num.group(1))
        self.assertGreater(col, 0.5 * 4 + 0.3 + 0.8)        # wide enough for "10.12", the widest number
        # (a) hangs under the text of 1.1, (i) under the text of (a)
        self.assertIn(f'<p class="cl" style="margin-left:{col:.2f}em;padding-left:2.00em;text-indent:-2.00em">'
                      '<span class="n" style="width:2.00em">(a)</span><strong>', out)
        self.assertRegex(out, rf'margin-left:{col + 2:.2f}em;padding-left:[\d.]+em;text-indent:-[\d.]+em"><span class="n"[^>]*>\(i\)</span>with its garden;')
        # a heading's number stands in the same column, and its words are a unit
        self.assertRegex(out, rf'<h2 class="cl" style="margin-left:0.00em;padding-left:{col:.2f}em;[^"]*"><span class="n"[^>]*>1\.</span><span class="t">DEFINITIONS</span></h2>')
        # a party "(1)" and a recital "A." hang at the margin
        self.assertRegex(out, r'<span class="n"[^>]*>\(1\)</span><strong>MUTALE PROPERTIES LIMITED</strong>')
        self.assertRegex(out, r'<span class="n"[^>]*>A\.</span>The Landlord owns the house\.')

    def test_setting_changes_no_word(self):
        plain = markdown.markdown(d.tidy_source(self.AGREEMENT), extensions=d.markdown_extensions("agreement"))
        self.assertEqual(words(set_(self.AGREEMENT, "agreement")), words(plain))
        plain = markdown.markdown(d.tidy_source(TYPED_HEADING), extensions=d.markdown_extensions("court"))
        got = words(set_(TYPED_HEADING, "court"))
        for word in ("MWILA HARDWARE LIMITED", "2ND DEFENDANT", "PETER TEMBO", "HOLDEN AT LUSAKA", "2026/HPC/0412",
                     "The Plaintiff is a limited liability company"):
            self.assertIn(word, got)

    def test_what_only_looks_like_a_number_is_left_alone(self):
        out = set_("17.11.2026 was the date.\n\nA. Banda signed.\n\n2.5 per cent is the rate.", "letter")
        self.assertNotIn('class="cl"', out)
        self.assertIn("<p>17.11.2026 was the date.</p>", out)
        self.assertIn("<p>2.5 per cent is the rate.</p>", out)
        self.assertIn("<p>A. Banda signed.</p>", out)       # an initial, not a recital, outside an agreement

    def test_clauses_typed_one_to_a_line_are_one_to_a_paragraph(self):
        out = set_("The deductions are:\n\n(a) rent unpaid;\n(b) damage;\n(c) utilities.\n", "agreement")
        self.assertEqual(out.count('<p class="cl"'), 3)


class Quotations(unittest.TestCase):
    RULE = " ".join(["In any suit for restraining the defendant from the committal of any breach of contract"] * 5)

    def test_a_long_quotation_is_lifted_out_and_indented(self):
        html = f'<p><strong>3.1.1</strong> Order 27 rule 4 provides as follows: "{self.RULE}." That is this case.</p>'
        out = d.normalise(html, "court")
        self.assertRegex(out, r'<span class="n"[^>]*>3\.1\.1</span>Order 27 rule 4 provides as follows:</p>')
        # indented under the text of its paragraph, between its own quotation marks
        self.assertRegex(out, r'<blockquote style="margin-left:[\d.]+em"><p>“In any suit.*contract\.”</p></blockquote>')
        self.assertRegex(out, r'<p class="cont" style="padding-left:[\d.]+em">That is this case\.</p>')
        self.assertIn("blockquote { font-weight: 700; }", d.COURT_CSS)      # bold italic, as the judgments have it
        self.assertEqual(words(out), words(html))

    def test_a_short_quotation_stays_in_its_sentence(self):
        html = '<p>The Court held that "an injunction would only be granted to a plaintiff with a good and arguable claim".</p>'
        self.assertNotIn("<blockquote", d.normalise(html, "court"))
        # and an agreement's defined terms are never lifted out
        self.assertNotIn("<blockquote", d.normalise(f'<p>1.1 "{self.RULE}" means the rule.</p>', "agreement"))

    def test_typewriter_marks_become_printers_marks(self):
        out = d.normalise("<p>\"the Premises\" means the Tenant's house, let on the 1st and the 22nd; "
                          "see <code>it's \"x\"</code>.</p>", "agreement")
        self.assertIn("“the Premises” means the Tenant’s house", out)
        self.assertIn("1<sup>st</sup> and the 22<sup>nd</sup>", out)
        self.assertIn("<code>it's \"x\"</code>", out)       # what is quoted as code is not touched
        # a defined term straight after its clause number opens with an opening mark
        out = d.normalise('<p>(a) <strong>"the Premises"</strong> means the house;</p>', "agreement")
        self.assertIn("</span><strong>\u201cthe Premises\u201d</strong>", out)


class Signing(unittest.TestCase):
    def test_underscores_inside_a_line_reach_the_page(self):
        body = "Signature: ______________________________\n\nPaid on ______ at ______.\n"
        self.assertNotIn("<strong>", markdown.markdown(d.tidy_source(body)))     # Markdown read them as emphasis
        self.assertEqual(d.tidy_source(d.tidy_source(body)), d.tidy_source(body))
        out = set_(body, "letter")
        self.assertEqual(out.count('<span class="rule"'), 3)
        # a court tool's own markup is not escaped: Markdown leaves raw HTML alone
        html_line = '<p class="dated">Dated this ______ day of ________</p>'
        self.assertEqual(d.tidy_source(html_line), html_line)

    def test_name_signature_date_become_an_aligned_block(self):
        body = ("# TENANCY AGREEMENT\n\n## 12. GENERAL\n\n12.1 This is the whole agreement.\n\n"
                "**SIGNED** for and on behalf of **MUTALE PROPERTIES LIMITED**:\n\nName: Joseph Mutale\n\nTitle: Director\n\n"
                "Signature: ______________________________\n\nDate: ______________________________\n\nIn the presence of:\n\n"
                "Witness name: ______________________\n\nNRC No.: ______________________\n\n"
                "**SIGNED** by **GRACE PHIRI**:\n\nSignature: ____________\n\nDate: ____________\n\n## SCHEDULE: INVENTORY\n\n"
                "| Room | Condition |\n|---|---|\n| | |\n| | |\n")
        out = set_(body, "agreement")
        self.assertIn('<table class="form"><tr><td class="lab">Name:</td><td class="val">Joseph Mutale</td></tr>'
                      '<tr><td class="lab">Title:</td><td class="val">Director</td></tr>'
                      '<tr><td class="lab">Signature:</td><td class="val open"></td></tr>'
                      '<tr><td class="lab">Date:</td><td class="val open"></td></tr></table>', out)
        self.assertIn("<p>In the presence of:</p>", out)     # words, not a line to fill in
        self.assertEqual(out.count('<div class="keep exec">'), 2)      # each party's block stays on one page
        self.assertIn('<h2 class="schedule">SCHEDULE: INVENTORY</h2>', out)      # a schedule starts a page
        self.assertEqual(out.count('<tr class="blank-row">'), 2)      # rows to write in have room
        # filled-in details with no line to sign are left as the lines they are
        self.assertNotIn("form", set_("Bank: Zanaco\nBranch: Cairo Road\nAccount number: 0123456789", "letter"))

    def test_a_letters_subject_line_is_marked(self):
        out = set_("Dear Sir,\n\n**RE: DEMAND FOR PAYMENT OF K25,000.00**\n\n**WITHOUT PREJUDICE**\n\nWe act.", "letter")
        self.assertIn('<p class="re-line"><strong>RE: DEMAND FOR PAYMENT OF K25,000.00</strong></p>', out)
        self.assertIn('<p class="marking"><strong>WITHOUT PREJUDICE</strong></p>', out)
        self.assertIn("text-decoration: underline", d.LETTER_CSS)

    def test_the_date_and_signature_of_a_court_document_stay_together(self):
        body = TYPED_HEADING + "\n\nDATED at LUSAKA this 17th day of November 2026.\n\n..............................\n**BANDA AND COMPANY**\nAdvocates for the Plaintiff\n"
        out = set_(body, "court", "STATEMENT OF CLAIM")
        self.assertRegex(out, r'<div class="keep ending"><p>DATED at LUSAKA this 17<sup>th</sup> day of November 2026\.</p>')
        self.assertRegex(out, r'<span class="rule dots"[^>]*></span><br>\s*<strong>BANDA AND COMPANY</strong><br>')

    def test_what_a_hand_completes_is_not_asked_for(self):
        self.assertEqual(d.find_blanks("[COMMISSIONER FOR OATHS] [JUDGE] [FIRM NAME]"), ["[FIRM NAME]"])

    def test_a_blank_named_for_the_first_or_second_defendant_is_a_blank(self):
        body = "resides at [2ND DEFENDANT ADDRESS], office at [1ST DEFENDANT REGISTERED OFFICE]; see [2024] ZMCA 278 and [1975] AC 396."
        self.assertEqual(d.find_blanks(body), ["[2ND DEFENDANT ADDRESS]", "[1ST DEFENDANT REGISTERED OFFICE]"])
        out, filled, missed = d.fill_blanks(body, {"2nd defendant address": "12 Ibex Hill, Lusaka"})
        self.assertIn("resides at 12 Ibex Hill, Lusaka,", out)
        self.assertEqual((filled, missed), (["[2ND DEFENDANT ADDRESS]"], []))
        self.assertEqual(d.mark_blanks("<p>" + body + "</p>").count('<span class="blank">'), 2)


class CourtTools(unittest.IsolatedAsyncioTestCase):
    async def _draft(self, tool: str, **args) -> str:
        made = {}

        async def keep(*, title, body_markdown, **kw):
            made["body"] = body_markdown
            return {"result": {"title": title, **pdf_tools.blanks_note(body_markdown)}}

        with patch.object(pdf_tools, "pdf_generate_legal", keep):
            reg = tools.build_tool_registry(owner_id=None, session_id=None)
            out = await reg[tool].handler(**args)
        self.result = out["result"]
        return made["body"]

    COMMON = dict(procedural_mode="Summons for an Order of Interim Injunction", court_division="Principal Registry, Civil",
                  applicant_name="Chanda Mulenga", respondent_name="Kafue Estates Limited", cause_number="2026/HP/1482")

    async def test_an_action_begun_by_writ_keeps_plaintiff_and_defendant(self):
        body = await self._draft("draft_affidavit", **self.COMMON, applicant_role="plaintiff", respondent_role="defendant",
                                 deponent_name="Chanda Mulenga", deponent_address="Plot 4521, Kabulonga, Lusaka",
                                 deponent_occupation="a teacher", facts=["I rent the house."],
                                 exhibits=[{"label": "CM1", "description": "The tenancy agreement"}])
        self.assertIn('<td class="role">PLAINTIFF</td>', body)
        self.assertIn("THAT I am the Plaintiff in this matter", body)
        self.assertNotIn("APPLICANT", body)
        # the words of Form H.C. Civ. 15, and nothing to ask the user about the Commissioner
        self.assertIn("make oath and say as follows:", body)
        self.assertIn('<table class="jurat">', body)
        self.assertIn("SWORN</strong> by the said<br/><strong>CHANDA MULENGA</strong>", body)
        self.assertIn("COMMISSIONER FOR OATHS", body)
        self.assertEqual(self.result["blanks"], [])
        # a sheet to mark each exhibit, under the short title of the cause (High Court Rules, O.V r.20(l))
        self.assertIn('<div class="exhibit-sheet"><p class="short-title">2026/HP/1482 Chanda Mulenga v Kafue Estates Limited</p>', body)
        self.assertIn('This is the exhibit marked "CM1" referred to in the Affidavit of', body)

    async def test_titles_read_from_the_kind_of_process_when_none_are_given(self):
        body = await self._draft("draft_order", **{**self.COMMON, "procedural_mode": "Petition"}, orders=["The petition is granted."])
        self.assertIn('<td class="role">PETITIONER</td>', body)
        self.assertIn('<div class="doc-title">ORDER</div>', body)
        self.assertIn("Dated at Lusaka this ............ day of", body)      # the court dates its own order

    async def test_skeleton_arguments_set_cases_in_bold_and_sign_at_the_foot(self):
        body = await self._draft(
            "draft_skeletal", **self.COMMON, applicant_role="PLAINTIFF", respondent_role="DEFENDANT",
            submissions=[{"title": "The test", "paragraphs": ["The leading authority is Shell and BP Zambia Limited v Conidaris and Others (1975) ZR 174."],
                          "citations": ["Shell and BP Zambia Limited v Conidaris and Others (1975) ZR 174 (SC)"]}],
            authorities_cases=["Shell and BP Zambia Limited v Conidaris and Others (1975) ZR 174 (SC)"], counsel_firm="Banda and Company")
        self.assertIn("<p>1.1.1 The leading authority is <strong>Shell and BP Zambia Limited v Conidaris and Others</strong> (1975) ZR 174.</p>", body)
        self.assertIn('<p class="authority">Authority: Shell and BP', body)
        self.assertIn("<h2>1.0 SUBMISSIONS</h2>", body)
        self.assertIn("<strong>BANDA AND COMPANY</strong></p><p>Advocates for the Plaintiff</p>", body)
        set_out = d.normalise(markdown.markdown(body, extensions=d.markdown_extensions("court")), "court")
        self.assertRegex(set_out, r'<h2 class="cl"[^>]*><span class="n"[^>]*>1\.0</span><span class="t">SUBMISSIONS</span></h2>')

    async def test_a_summons_says_who_took_it_out_and_on_whom_it_is_served(self):
        body = await self._draft("draft_summons", **self.COMMON, applicant_role="PLAINTIFF", respondent_role="DEFENDANT",
                                 reliefs=["An injunction."], counsel_firm="Banda and Company",
                                 firm_address="Plot 14 Cairo Road, Lusaka", respondent_address="Plot 9 Great East Road, Lusaka")
        self.assertIn("This Summons for an Order of Interim Injunction was taken out by <strong>Banda and Company</strong> "
                      "of Plot 14 Cairo Road, Lusaka, Advocates for the Plaintiff.", body)
        self.assertIn("<strong>To:</strong> Kafue Estates Limited, the Defendant, of Plot 9 Great East Road, Lusaka.", body)
        self.assertRegex(body, r"Dated at Lusaka this \d{1,2}(st|nd|rd|th) day of [A-Z][a-z]+, 20\d\d\.")
        self.assertNotIn("The Registrar", body)

    async def test_a_party_with_no_advocate_signs_in_person(self):
        body = await self._draft("draft_summons", **self.COMMON, applicant_role="PLAINTIFF", respondent_role="DEFENDANT",
                                 reliefs=["An injunction."], in_person=True, applicant_address="Plot 4521, Kabulonga, Lusaka")
        self.assertIn("<strong>CHANDA MULENGA</strong></p><p>Plaintiff in person</p><p>Plot 4521, Kabulonga, Lusaka</p>", body)
        self.assertIn("taken out by <strong>Chanda Mulenga</strong>, the Plaintiff in person, of Plot 4521, Kabulonga, Lusaka.", body)
        self.assertNotIn("FIRM", body)                      # nothing to ask a litigant in person about a firm
        body = await self._draft("draft_order", **self.COMMON, orders=["Granted."], counsel_firm="Banda and Company")
        self.assertIn("Drawn by:</strong><br/>Banda and Company<br/>[FIRM ADDRESS FOR SERVICE]<br/>Advocates for the Applicant", body)

    async def test_a_pleading_sent_to_the_memo_tool_is_set_as_a_court_document(self):
        got = {}

        async def keep(**kw):
            got.update(kw)
            return {"result": {"artifact_id": "x"}}

        with patch.object(pdf_tools, "pdf_generate_legal", keep):
            await pdf_tools.pdf_generate("STATEMENT OF CLAIM", TYPED_HEADING, owner_id="u1", session_id="s1")
        self.assertEqual((got["layout"], got["meta_tool"], got["extra_meta"]), ("court", "pdf_generate", {"doc_title": "STATEMENT OF CLAIM"}))
        self.assertEqual(got["title"], "STATEMENT OF CLAIM")


class Word(unittest.TestCase):
    def _doc(self, body: str, layout: str, **kw):
        import docx
        return docx.Document(io.BytesIO(docx_tools.render_docx_bytes(title="x", body_md=body, legal=True, layout=layout, **kw)))

    def test_a_court_document_opens_in_word_set_like_the_pdf(self):
        long_quote = " ".join(["the right to relief is clear and the injunction is necessary"] * 6)
        doc = self._doc(TYPED_HEADING + f'\n\n2.1 The Court held: "{long_quote}."\n\n(a) first;\n', "court", title_hint="STATEMENT OF CLAIM")
        self.assertEqual(doc.styles["Normal"].font.name, "Bookman Old Style")
        sec = doc.sections[0]
        self.assertEqual((round(sec.left_margin.mm), round(sec.right_margin.mm), round(sec.page_width.mm)), (40, 20, 210))
        caption, parties = doc.tables[0], doc.tables[1]
        self.assertEqual([c.text for c in caption.rows[0].cells][1], "2026/HPC/0412")
        self.assertIn("IN THE HIGH COURT FOR ZAMBIA\nAT THE COMMERCIAL REGISTRY", caption.rows[0].cells[0].text)
        self.assertNotEqual(caption.style.name, "Table Grid")           # a heading has no ruled lines
        self.assertEqual([c.text for c in parties.rows[0].cells], ["MWILA HARDWARE LIMITED", "PLAINTIFF"])
        texts = [p.text for p in doc.paragraphs]
        self.assertIn("STATEMENT OF CLAIM", texts)
        clause = next(p for p in doc.paragraphs if p.text.startswith("2.1\t"))
        self.assertLess(clause.paragraph_format.first_line_indent.pt, 0)      # the number hangs
        quote = next(p for p in doc.paragraphs if p.text.startswith("“the right to relief"))
        self.assertTrue(all(r.italic and r.bold for r in quote.runs if r.text.strip()))
        self.assertGreater(quote.paragraph_format.right_indent.pt, 0)
        self.assertIn("PAGE", doc.sections[0].footer._element.xml)

    def test_lines_to_sign_are_ruled_in_word_too(self):
        doc = self._doc("**SIGNED** by **GRACE PHIRI**:\n\nName: Grace Phiri\n\nSignature: ____________\n", "agreement")
        form = doc.tables[0]
        self.assertEqual([c.text for c in form.rows[0].cells], ["Name:", "Grace Phiri"])
        self.assertIn("w:bottom", form.rows[1].cells[1]._tc.xml)          # a ruled space to sign in


if __name__ == "__main__":
    unittest.main()
