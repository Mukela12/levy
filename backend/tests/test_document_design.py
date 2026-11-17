"""How Levy's documents are set, which blanks they carry, and how they get filled.

A review of the 170 documents Levy had generated for users (17 Nov 2026) found
sound but plain layouts, a grey subtitle under every memo's title, notes to the
drafter printed inside documents, and 145 documents handed over with blanks
that often stayed blank after the user supplied the details.
"""
import io
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services import agent, doc_design as d, docx_tools, templates, tools  # noqa: E402


class Layout(unittest.TestCase):
    def test_each_kind_of_document_gets_its_own_layout(self):
        self.assertEqual(d.infer_layout('<div class="court-caption">IN THE HIGH COURT FOR ZAMBIA</div>'), "court")
        self.assertEqual(d.infer_layout("## IN THE SUBORDINATE COURT FOR ZAMBIA\n\n**CIVIL CAUSE No.**"), "court")
        self.assertEqual(d.infer_layout("**Date:** 3 March 2026\n\n## RE: NOTICE OF REDUNDANCY\n\nDear Mary,"), "letter")
        self.assertEqual(d.infer_layout("# CONSULTANCY SERVICES AGREEMENT\n\n**THIS AGREEMENT** is made on"), "agreement")
        # an agreement that happens to say "Date:" is still an agreement
        self.assertEqual(d.infer_layout("## LEASE\n\n**THIS LEASE** is made\n\nDate: 1 May 2026"), "agreement")

    def test_court_papers_follow_the_rules_that_exist(self):
        # Constitutional Court Rules 2016 r.11: A4, not less than 4 cm on the left.
        self.assertIn("size: A4", d.COURT_CSS)
        self.assertIn("margin: 25mm 25mm 25mm 40mm", d.COURT_CSS)
        self.assertIn("font-size: 12pt", d.COURT_CSS)
        self.assertIn("Times New Roman", d.COURT_CSS)

    def test_no_layout_uses_colour(self):
        for css in (d.COURT_CSS, d.AGREEMENT_CSS, d.LETTER_CSS, d.MEMO_CSS):
            colours = {c.lower() for c in __import__("re").findall(r"#[0-9a-fA-F]{3,6}", css)}
            self.assertLessEqual(colours, {"#000", "#777", "#fff1b8"}, colours)

    def test_headings_are_evened_out_and_only_one_is_the_title(self):
        html = "<h2>SETTLEMENT AGREEMENT</h2><p><strong>BETWEEN</strong></p><h3>1. Interpretation</h3><h3>2. Payment</h3>"
        out = d.normalise(html, "agreement")
        self.assertIn("<h1>SETTLEMENT AGREEMENT</h1>", out)
        self.assertIn('<p class="connective">BETWEEN</p>', out)
        self.assertEqual(out.count("<h2>"), 2)
        # clauses written as top-level headings, with no title heading, are clauses
        out = d.normalise("<p><strong>LEASE</strong></p><h2>1. Term</h2><p>x</p><h2>2. Rent</h2>", "agreement")
        self.assertEqual((out.count("<h1>"), out.count("<h2>")), (0, 2))

    def test_a_letters_sign_off_stays_with_the_name_under_it(self):
        out = d.normalise("<p>Body.</p><p>Yours faithfully,</p><p>Mutale Zimba<br/>HR Manager</p>", "letter")
        self.assertIn('<div class="keep"><p>Yours faithfully,</p><p>Mutale Zimba<br/>HR Manager</p></div>', out)
        self.assertIn(".keep { break-inside: avoid; }", d.LETTER_CSS.replace("tr, .sig-block, .attestation, .keep", ".keep"))

    def test_letters_and_agreements_keep_their_line_breaks(self):
        self.assertIn("nl2br", d.markdown_extensions("letter"))
        self.assertNotIn("nl2br", d.markdown_extensions("court"))


class Blanks(unittest.TestCase):
    def test_what_is_a_blank_and_what_is_not(self):
        body = ("Dear [EMPLOYEE FULL NAME], on [DATE OF LETTER] and again [EMPLOYEE FULL NAME]. "
                "[DESCRIBE ROLE, e.g. student counselling]. See [2024] ZMCA 278, [SI No. 49 of 2023, para 8], "
                "[APP No. 171 of 2019] and [Employment Code Act, s.36]. Sign at [SEAL] and [SIGNATURE].")
        self.assertEqual(d.find_blanks(body), ["[EMPLOYEE FULL NAME]", "[DATE OF LETTER]",
                                               "[DESCRIBE ROLE, e.g. student counselling]"])

    def test_filling_replaces_every_occurrence_and_reports_what_did_not_match(self):
        body = "**To:** [EMPLOYEE FULL NAME]\n\nDear [EMPLOYEE FULL NAME], your hearing is on [HEARING DATE] at [VENUE]."
        out, filled, unmatched = d.fill_blanks(body, {"employee full name": "Mary Banda", "[Hearing Date]": "1 December 2026",
                                                      "PANEL": "Mr Phiri"})
        self.assertEqual(out, "**To:** Mary Banda\n\nDear Mary Banda, your hearing is on 1 December 2026 at [VENUE].")
        self.assertEqual(filled, ["[EMPLOYEE FULL NAME]", "[HEARING DATE]"])
        self.assertEqual(unmatched, ["PANEL"])
        self.assertEqual(d.find_blanks(out), ["[VENUE]"])

    def test_blanks_are_marked_on_the_page_but_tags_and_citations_are_left_alone(self):
        html = d.mark_blanks('<p>Dear [EMPLOYEE FULL NAME], see <a href="x[A]">[2024] ZMCA 5</a>, paragraph [__].</p>')
        self.assertEqual(html.count('<span class="blank">'), 2)
        self.assertIn('href="x[A]"', html)
        self.assertIn(">[2024] ZMCA 5<", html)

    def test_the_tool_result_tells_the_model_what_is_missing(self):
        from app.services import pdf_tools
        note = pdf_tools.blanks_note("Dear [EMPLOYEE FULL NAME], on [DATE OF LETTER].")
        self.assertEqual((note["blank_count"], note["complete"]), (2, False))
        self.assertIn("fill_document", note["next_step"])
        self.assertEqual(pdf_tools.blanks_note("Dear Mary, on 1 May 2026."), {"blanks": [], "complete": True})


class Letterhead(unittest.TestCase):
    def logo(self) -> bytes:
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (1600, 600), (20, 60, 40)).save(buf, format="PNG")
        return buf.getvalue()

    def test_a_logo_upload_is_a_template_type(self):
        self.assertEqual(templates.file_type_for("Logo.PNG"), "png")
        self.assertEqual(templates.file_type_for("mark.jpeg"), "jpg")
        self.assertEqual(templates.extract_preview(self.logo(), "png"), ("", None))

    def test_a_logo_is_shrunk_and_an_unreadable_one_is_dropped(self):
        png, mime = templates.normalise_logo(self.logo())
        from PIL import Image
        self.assertLessEqual(Image.open(io.BytesIO(png)).size[0], 900)
        self.assertEqual(mime, "image/png")
        self.assertIsNone(templates.normalise_logo(b"not an image"))

    def test_a_logo_template_prints_the_logo_and_the_details_from_its_description(self):
        row = {"id": "t1", "name": "Our logo", "file_type": "png", "storage_path": "templates/u/x.png",
               "description": "Kafue Traders Limited\nPlot 12, Cairo Road, Lusaka\nTel: 0211 000000", "preview_text": None}
        templates._LH_CACHE.clear()
        with patch.object(templates, "get_template_by_id", lambda o, t: row), \
                patch.object(templates, "download_template", lambda t: self.logo()):
            lh = templates.letterhead_of("u1", "t1")
        self.assertEqual(lh["lines"][0], "Kafue Traders Limited")
        self.assertTrue(lh["logo"])
        html = d.letterhead_html(lh)
        self.assertIn('class="letterhead"', html)
        self.assertIn("data:image/png;base64,", html)
        self.assertIn('<div class="lh-name">Kafue Traders Limited</div>', html)

    def test_a_word_template_gives_its_header_text_and_logo_and_itself(self):
        from docx import Document
        from docx.shared import Mm
        doc = Document()
        hdr = doc.sections[0].header
        hdr.paragraphs[0].text = "MWANSA & CO. ADVOCATES"
        hdr.add_paragraph("Plot 5, Independence Avenue, Lusaka")
        hdr.paragraphs[0].add_run().add_picture(io.BytesIO(self.logo()), height=Mm(15))
        doc.add_paragraph("[DATE]")
        doc.add_paragraph("Dear Sir,")
        buf = io.BytesIO()
        doc.save(buf)
        row = {"id": "t2", "name": "Firm letter", "file_type": "docx", "storage_path": "templates/u/y.docx",
               "description": None, "preview_text": "[DATE]\nDear Sir,"}
        templates._LH_CACHE.clear()
        with patch.object(templates, "get_template_by_id", lambda o, t: row), \
                patch.object(templates, "download_template", lambda t: buf.getvalue()):
            lh = templates.letterhead_of("u1", "t2")
        self.assertEqual(lh["lines"], ["MWANSA & CO. ADVOCATES", "Plot 5, Independence Avenue, Lusaka"])
        self.assertTrue(lh["logo"] and lh["docx"])
        # the Word export is written inside the user's own file: header kept, old body gone
        marker = d.letterhead_marker("11111111-1111-1111-1111-111111111111")
        with patch.object(templates, "letterhead_of", lambda o, t: lh):
            out = docx_tools.render_docx_bytes(title="Letter", legal=True, owner_id="u1",
                                               body_md=marker + "\n\n**[COMPANY LETTERHEAD]**\n\n## RE: DEMAND\n\nDear Madam,\n\nPay.")
        made = Document(io.BytesIO(out))
        self.assertEqual(made.sections[0].header.paragraphs[0].text, "MWANSA & CO. ADVOCATES")
        text = "\n".join(p.text for p in made.paragraphs)
        self.assertIn("RE: DEMAND", text)
        self.assertNotIn("Dear Sir", text)
        self.assertNotIn("LETTERHEAD", text)

    def test_the_body_stores_a_marker_not_the_logo(self):
        from app.services import pdf_tools
        mark = pdf_tools.render_template_letterhead({"id": "11111111-1111-1111-1111-111111111111"})
        self.assertEqual(d.LETTERHEAD_MARK.findall(mark), ["11111111-1111-1111-1111-111111111111"])
        self.assertEqual(pdf_tools.render_template_letterhead(None), "")
        with patch.object(templates, "letterhead_of", lambda o, t: None):
            body, lh = pdf_tools.resolve_letterhead(mark + "\n\n**[COMPANY LETTERHEAD]**\n\nDear Sir", "u1")
        self.assertIsNone(lh)
        self.assertIn("[COMPANY LETTERHEAD]", body)      # no letterhead on file: the blank stays to be asked for
        self.assertNotIn("data-levy-letterhead", body)


class Word(unittest.TestCase):
    def test_the_word_file_is_set_like_the_pdf(self):
        from docx import Document
        out = docx_tools.render_docx_bytes(
            title="x", legal=True,
            body_md="# SERVICE AGREEMENT\n\n**BETWEEN**\n\n## 1. Term\n\nThis runs from [START DATE].")
        doc = Document(io.BytesIO(out))
        self.assertEqual(doc.styles["Normal"].font.name, "Book Antiqua")
        runs = [r for p in doc.paragraphs for r in p.runs]
        title = next(r for r in runs if r.text == "SERVICE AGREEMENT")
        self.assertEqual((title.font.name, str(title.font.color.rgb)), ("Book Antiqua", "000000"))
        blank = next(r for r in runs if r.text == "[START DATE]")
        self.assertIsNotNone(blank.font.highlight_color)
        court = Document(io.BytesIO(docx_tools.render_docx_bytes(
            title="x", legal=True, body_md='<div class="court-caption">IN THE HIGH COURT FOR ZAMBIA</div>\n\n1. THAT I am the Applicant.')))
        self.assertEqual(court.styles["Normal"].font.name, "Times New Roman")

    def test_a_memo_has_no_subtitle(self):
        from docx import Document
        out = docx_tools.render_docx_bytes(title="Advice on notice", body_md="## 1. Question\n\nText.", subtitle="Revised edition")
        text = "\n".join(p.text for p in Document(io.BytesIO(out)).paragraphs)
        self.assertNotIn("Revised edition", text)


class Tools(unittest.IsolatedAsyncioTestCase):
    def test_the_tools_and_the_prompt_agree(self):
        reg = tools.build_tool_registry(owner_id=None, session_id=None)
        self.assertIn("fill_document", reg)
        self.assertIn("save_letterhead", reg)
        self.assertNotIn("subtitle", reg["pdf_generate"].input_schema["properties"])
        self.assertIn("layout", reg["draft_legal_document"].input_schema["properties"])
        p = agent.AGENT_SYSTEM_SUFFIX
        for must in ("`fill_document`", "`save_letterhead`", "ONLY THE DOCUMENT GOES IN THE DOCUMENT",
                     "A fact you were given never appears as a blank"):
            self.assertIn(must, p)
        section = p[p.index("BLANKS: USE EVERYTHING YOU KNOW"):p.index("IF A TOOL GENUINELY CANNOT")]
        self.assertNotIn("—", section)

    async def test_filling_a_draft_renders_the_finished_document(self):
        from app.services import pdf_tools
        row = {"id": "11111111-1111-1111-1111-111111111111", "title": "Notice", "owner_id": "u1", "session_id": "s1",
               "meta": {"layout": "legal", "format": "letter", "tool": "draft_legal_document",
                        "source_markdown": "Dear [EMPLOYEE FULL NAME], your hearing is on [HEARING DATE]."}}

        class Q:
            def __getattr__(self, name):
                return lambda *a, **k: self

            def execute(self):
                return types.SimpleNamespace(data=[row])
        made = {}

        async def fake_legal(**kw):
            made.update(kw)
            return {"result": {"artifact_id": "new", **pdf_tools.blanks_note(kw["body_markdown"])}, "artifact": {}}
        with patch.object(pdf_tools, "get_db", lambda: types.SimpleNamespace(table=lambda n: Q())), \
                patch.object(pdf_tools, "pdf_generate_legal", fake_legal):
            out = await pdf_tools.fill_document(row["id"], {"[EMPLOYEE FULL NAME]": "Mary Banda"}, owner_id="u1")
            self.assertEqual(made["body_markdown"], "Dear Mary Banda, your hearing is on [HEARING DATE].")
            self.assertEqual((made["layout"], made["extra_meta"]), ("letter", {"filled_from": row["id"]}))
            self.assertEqual(out["result"]["filled"], ["[EMPLOYEE FULL NAME]"])
            self.assertEqual(out["result"]["blanks"], ["[HEARING DATE]"])
            done = await pdf_tools.fill_document(row["id"], {"employee full name": "Mary Banda", "hearing date": "1 Dec 2026"}, owner_id="u1")
            self.assertTrue(done["result"]["complete"])
            self.assertIn("complete", done["result"]["next_step"])
            other = await pdf_tools.fill_document(row["id"], {"[X]": "y"}, owner_id="someone-else")
            self.assertIn("another account", other["result"]["error"])
            none = await pdf_tools.fill_document(row["id"], {"[NOT THERE]": "y"}, owner_id="u1")
            self.assertIn("[HEARING DATE]", none["result"]["blanks"])


if __name__ == "__main__":
    unittest.main()
