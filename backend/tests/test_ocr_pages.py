"""OCR'd judgments keep their page numbers (scripts/ocr_backfill_tesseract.py).

The OCR sidecar separates pages with form feeds; joining them before chunking
stamped every chunk "page 1", so an answer could not cite the page a holding
is on (35 of the 39 newest judgments on 14 Oct 2026).
"""
import sys
import types
import unittest
from pathlib import Path

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import ocr_backfill_tesseract as ocr  # noqa: E402


class ChunkPages(unittest.TestCase):
    def test_each_chunk_carries_its_pages(self):
        pages = ["Heading on page one.\n\nFirst holding.", "", "Third page reasoning."]
        out = ocr.chunk_pages(pages, target=40)
        # 40-character target: page one fills a chunk, the blank page is skipped.
        self.assertEqual([(c["page_start"], c["page_end"]) for c in out], [(1, 1), (3, 3)])

    def test_a_chunk_spanning_a_page_break_records_both(self):
        out = ocr.chunk_pages(["End of page one.", "Start of page two."], target=1100)
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]["page_start"], out[0]["page_end"]), (1, 2))

    def test_a_long_paragraph_is_cut_on_its_own_page(self):
        out = ocr.chunk_pages(["Short.", "x" * 5000], target=1100)
        self.assertEqual(out[0]["page_start"], 1)
        self.assertTrue(all(c["page_start"] == 2 for c in out[1:]))
        self.assertEqual("".join(c["text"] for c in out[1:]).count("x"), 5000)

    def test_same_words_as_the_old_chunker(self):
        # A page break is now a paragraph break; the words and their order are unchanged.
        pages = ["Para one.\n\nPara two is longer than one.", "Para three.\n\nPara four."]
        words = lambda texts: " ".join(" ".join(texts).split())
        self.assertEqual(words(c["text"] for c in ocr.chunk_pages(pages)), words(ocr.chunk_text("\n".join(pages))))


if __name__ == "__main__":
    unittest.main()
