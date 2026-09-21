"""A scanned judgment must not become a title-only row.

`ingest_form_pdf` deliberately stores a synthesised header when a PDF has no
readable text, so an image-only PACRA form still turns up in search and the
person opens the file to fill it in. Applied to a judgment that behaviour put
cases in the corpus that Levy knew the name of and could not quote a word
from. These tests pin the difference.
"""
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from unittest.mock import MagicMock

from app.db import supabase as supabase_db
from app.services import form_ingester
from app.services.form_ingester import NeedsOcr, ingest_form_pdf


SCAN = ["", "  ", "\n"]                      # what pypdf returns for an image-only PDF
STAMPED_SCAN = ["REPUBLIC OF ZAMBIA", "J2"]  # a scan is rarely empty: stray marks survive
REAL = ["IN THE COURT OF APPEAL OF ZAMBIA\n" + "the judgment of the court. " * 40]


class Guard(unittest.TestCase):
    def setUp(self):
        self.calls = []
        for name, value in [("get_pdf_hash", lambda p: "hash"),
                            ("get_document_by_hash", lambda h: None),
                            ("get_embeddings", lambda texts: [[0.0] * 768 for _ in texts])]:
            patcher = patch.object(form_ingester, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        made = patch.object(form_ingester, "insert_document",
                            lambda row: self.calls.append(row) or {"id": "doc-1", **row})
        made.start()
        self.addCleanup(made.stop)
        chunks = patch.object(form_ingester, "insert_chunks",
                              lambda rows: [dict(r) for r in rows])
        chunks.start()
        self.addCleanup(chunks.stop)

    def _ingest(self, pages, **kw):
        # get_db is imported inside the function body, so it has to be patched
        # where it lives. Without this the test writes to the real database.
        with patch.object(form_ingester, "_read_pages", lambda path: pages), \
             patch.object(supabase_db, "get_db", MagicMock()):
            return ingest_form_pdf("/tmp/case.pdf", title="Some v Other", **kw)

    def test_a_scanned_judgment_is_refused(self):
        with self.assertRaises(NeedsOcr) as caught:
            self._ingest(SCAN, document_type="judgment")
        self.assertIn("OCR it", str(caught.exception))

    def test_a_refused_judgment_writes_nothing(self):
        # The row must not exist, or the next audit counts it as held.
        with self.assertRaises(NeedsOcr):
            self._ingest(SCAN, document_type="judgment")
        self.assertEqual(self.calls, [])

    def test_a_registry_stamp_is_not_a_text_layer(self):
        with self.assertRaises(NeedsOcr) as caught:
            self._ingest(STAMPED_SCAN, document_type="judgment")
        self.assertEqual(caught.exception.characters,
                         sum(len(p.strip()) for p in STAMPED_SCAN))

    def test_a_judgment_with_text_goes_through(self):
        out = self._ingest(REAL, document_type="judgment")
        self.assertEqual(out["status"], "success")
        self.assertEqual(len(self.calls), 1)

    def test_a_scanned_form_is_still_stored(self):
        # The original behaviour, unchanged: the person opens the PDF.
        out = self._ingest(SCAN, document_type="form")
        self.assertEqual(out["status"], "success")
        self.assertEqual(out["chunks_created"], 1)

    def test_ocr_follows_lets_the_row_be_made(self):
        # harvest_court_decisions.py OCRs into the row it just created.
        out = self._ingest(SCAN, document_type="judgment", ocr_follows=True)
        self.assertEqual(out["status"], "success")
        self.assertEqual(out["chunks_created"], 1)


if __name__ == "__main__":
    unittest.main()
