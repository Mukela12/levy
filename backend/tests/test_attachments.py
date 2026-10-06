"""Every attachment's status is honest: read, searchable, or NOT READ and why.

Twice a user attached a document whose text never reached the model; small
attachments were listed as "inline" whether or not any text had loaded.
"""
import sys
import types
import unittest

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services.attachments import INLINE_TOTAL_CAP, attachment_block, looks_scanned  # noqa: E402

TYPED = "The Respondent shall pay the Complainant the sum of K12,000 as gratuity. " * 30


def row(i, pages=2, chunks=0, name=None):
    return {"id": f"doc-{i}", "title": name or f"File {i}", "short_name": "", "pdf_page_count": pages,
            "total_chunks": chunks}


class Scans(unittest.TestCase):
    def test_a_typed_page_is_not_a_scan(self):
        self.assertFalse(looks_scanned(TYPED, 1))

    def test_a_scan_or_a_stamp_is(self):
        self.assertTrue(looks_scanned("", 3))
        self.assertTrue(looks_scanned("RECEIVED 12 AUG 2026", 2))


class Block(unittest.TestCase):
    def test_a_scan_is_marked_not_read_with_the_way_to_read_it(self):
        b = attachment_block([row(1, name="Contract scan")], {"doc-1": ""})
        self.assertIn('"Contract scan" (2 pages, NOT READ: no text layer', b)
        self.assertIn("document_id doc-1", b)
        self.assertIn("read_pdf_pages", b)
        self.assertIn("Never describe, summarise or rely on a document you have not read", b)
        self.assertNotIn("## Inline attachment contents", b)

    def test_readable_text_is_included_and_said_to_be(self):
        b = attachment_block([row(1, name="Letter")], {"doc-1": TYPED})
        self.assertIn('"Letter" (2 pages, full text below)', b)
        self.assertIn("### Attachment: Letter", b)
        self.assertNotIn("NOT READ", b)

    def test_a_document_past_the_budget_is_not_dropped_silently(self):
        # 30,000 characters each, 60,000 a turn: the third document overflows.
        big = "word " * (INLINE_TOTAL_CAP // 5 + 10)
        b = attachment_block([row(1), row(2), row(3, name="Third")], {"doc-1": big, "doc-2": big, "doc-3": TYPED})
        self.assertEqual(b.count("full text below, truncated"), 2)
        self.assertIn('"Third" (2 pages, NOT READ: past this turn\'s size limit; document_id doc-3)', b)

    def test_a_large_document_is_searchable(self):
        b = attachment_block([row(1, pages=40, chunks=120, name="Record of appeal")], {})
        self.assertIn('"Record of appeal" (40 pages, searchable: use search_corpus)', b)
        self.assertNotIn("NOT READ", b)


if __name__ == "__main__":
    unittest.main()
