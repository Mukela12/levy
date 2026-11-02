"""Attachments reach the model in the user's own turn, with their text, and each
one's status is honest: read, cut short, or NOT READ and why.

Twice a user attached a document whose text never reached the model; small
attachments were listed as "inline" whether or not any text had loaded. On
23 October 2026 a six-page upload was a single line at the end of the system
prompt ("searchable: use search_corpus"), and the reply said nothing had been
attached. Its chunks held 9,300 of the PDF's 15,400 characters.
"""
import sys
import types
import unittest

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

import pymupdf  # noqa: E402

from app.services.attachments import (  # noqa: E402
    INLINE_MAX_CHARS, INLINE_TOTAL_CAP, Attachment, attachment_turn_block, extract_pdf_text,
    load_attachments, looks_scanned,
)

TYPED = "The Respondent shall pay the Complainant the sum of K12,000 as gratuity. " * 30


def pdf_of(pages: list[str]) -> bytes:
    """A born-digital PDF with one paragraph of text per page."""
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=9)
    return doc.tobytes()


class FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def select(self, *_):
        return self

    def in_(self, col, values):
        self.rows = [r for r in self.rows if r.get(col) in values]
        return self

    def eq(self, col, value):
        self.rows = [r for r in self.rows if r.get(col) == value]
        return self

    def order(self, col, desc=False):
        self.rows.sort(key=lambda r: r.get(col), reverse=desc)
        return self

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    def execute(self):
        return types.SimpleNamespace(data=self.rows)


class FakeBucket:
    def __init__(self, objects):
        self.objects = objects

    def download(self, key):
        if key not in self.objects:
            raise RuntimeError("Object not found")
        return self.objects[key]


class FakeDb:
    """legal_documents, legal_chunks and the legal-docs bucket."""

    def __init__(self, documents, chunks=(), objects=None):
        self.tables = {"legal_documents": list(documents), "legal_chunks": list(chunks)}
        self.objects = objects or {}
        self.storage = types.SimpleNamespace(from_=lambda bucket: FakeBucket(self.objects))

    def table(self, name):
        return FakeQuery(self.tables[name])


def doc(i, **kw):
    return {"id": f"doc-{i}", "title": f"File {i}", "short_name": "", "pdf_page_count": 2,
            "total_chunks": 0, "pdf_storage_path": None, "owner_id": "user-1", **kw}


class Scans(unittest.TestCase):
    def test_a_typed_page_is_not_a_scan(self):
        self.assertFalse(looks_scanned(TYPED, 1))

    def test_a_scan_or_a_stamp_is(self):
        self.assertTrue(looks_scanned("", 3))
        self.assertTrue(looks_scanned("RECEIVED 12 AUG 2026", 2))


class Block(unittest.TestCase):
    def test_the_document_is_in_front_of_the_question_with_its_text(self):
        b = attachment_turn_block([Attachment("doc-1", "Letter", 2, TYPED, True, "stored")])
        self.assertTrue(b.startswith("<attachments>"))
        self.assertIn("attached this document to the message below", b)
        self.assertIn("never say that nothing was attached or pasted", b)
        self.assertIn('<document name="Letter" document_id="doc-1" pages="2" status="full text">', b)
        self.assertIn(TYPED.strip(), b)
        self.assertNotIn("NOT READ", b)

    def test_a_scan_is_marked_not_read_with_the_way_to_read_it(self):
        b = attachment_turn_block([Attachment("doc-1", "Contract scan", 3)])
        self.assertIn('name="Contract scan" document_id="doc-1" pages="3" status="NOT READ"', b)
        self.assertIn("read_pdf_pages", b)
        self.assertIn("Never describe, summarise or rely on a document you have not read", b)

    def test_space_runs_out_in_order_and_says_so(self):
        big = "word " * (INLINE_MAX_CHARS // 5)
        b = attachment_turn_block([Attachment(f"doc-{i}", f"File {i}", 9, big, True, "stored") for i in (1, 2, 3)])
        self.assertEqual(b.count('status="full text"'), 2)
        self.assertIn('document_id="doc-3" pages="9" status="NOT INCLUDED"', b)
        self.assertLessEqual(b.count("word"), INLINE_TOTAL_CAP // 5)

    def test_a_document_cut_short_says_where_the_rest_is(self):
        b = attachment_turn_block([Attachment("doc-1", "Record", 40, "x" * 100, False, "pdf")])
        self.assertIn('status="opening only"', b)
        self.assertIn("Read the rest with read_pdf_pages", b)

    def test_text_from_the_search_index_says_it_can_leave_parts_out(self):
        b = attachment_turn_block([Attachment("doc-1", "Act", None, "Section 1", True, "index")])
        self.assertIn("search index of the document, which can leave parts out", b)
        self.assertNotIn("pages=", b)

    def test_an_earlier_attachment_is_offered_for_the_follow_up(self):
        letter = Attachment("doc-1", "Letter", 2, TYPED, True, "stored")
        b = attachment_turn_block([], [letter])
        self.assertTrue(b.startswith("<earlier_attachments>"))
        self.assertIn("Earlier in this chat the user attached this document", b)
        self.assertIn(TYPED.strip(), b)
        # The same document attached again now is shown once, as current.
        both = attachment_turn_block([letter], [letter])
        self.assertEqual(both.count('document_id="doc-1"'), 1)
        self.assertNotIn("<earlier_attachments>", both)

    def test_quotes_in_a_name_cannot_break_the_tag(self):
        b = attachment_turn_block([Attachment("doc-1", 'The "Final"\nLetter', 1, TYPED, True, "stored")])
        self.assertIn("name=\"The 'Final' Letter\"", b)

    def test_nothing_attached_is_nothing(self):
        self.assertEqual(attachment_turn_block([], []), "")


class Loading(unittest.TestCase):
    def test_the_stored_text_comes_first(self):
        db = FakeDb([doc(1)], objects={"doc-1.txt": TYPED.encode()})
        [a] = load_attachments(db, ["doc-1"])
        self.assertEqual((a.source, a.complete, a.text), ("stored", True, TYPED.strip()))

    def test_an_upload_without_stored_text_is_read_from_its_pdf(self):
        # The 23 October shape: chunked, no page count, no text file, and
        # chunks holding only what the Act parser took for sections.
        pages = [f"Page {n}. " + ("The employer shall pay overtime at one and a half times. " * 20) for n in range(1, 7)]
        db = FakeDb([doc(1, total_chunks=5, pdf_page_count=None, pdf_storage_path="legal-docs/doc-1.pdf")],
                    chunks=[{"document_id": "doc-1", "chunk_index": 0, "content": "Section 3 only"}],
                    objects={"doc-1.pdf": pdf_of(pages)})
        [a] = load_attachments(db, ["doc-1"])
        self.assertEqual((a.source, a.pages, a.complete), ("pdf", 6, True))
        self.assertIn("Page 1.", a.text)      # the pages the parser dropped
        self.assertIn("Page 6.", a.text)
        self.assertNotIn("Section 3 only", a.text)

    def test_a_long_upload_is_read_only_as_far_as_it_will_be_shown(self):
        pages = ["Clause. " * 600] * 30
        text, complete, read, count = extract_pdf_text(pdf_of(pages), 10_000)
        self.assertFalse(complete)
        self.assertEqual(count, 30)
        self.assertLess(read, 10)
        self.assertGreater(len(text), 10_000)

    def test_a_library_document_falls_back_to_its_chunks_in_order(self):
        db = FakeDb([doc(1, owner_id=None, total_chunks=2)],
                    chunks=[{"document_id": "doc-1", "chunk_index": 1, "content": "Section 2. Leave."},
                            {"document_id": "doc-1", "chunk_index": 0, "content": "Section 1. Hours."}])
        [a] = load_attachments(db, ["doc-1"])
        self.assertEqual(a.source, "index")
        self.assertEqual(a.text, "Section 1. Hours.\n\nSection 2. Leave.")
        self.assertTrue(a.complete)

    def test_a_stamp_is_not_taken_for_text(self):
        db = FakeDb([doc(1)], objects={"doc-1.txt": b"RECEIVED 12 AUG 2026"})
        [a] = load_attachments(db, ["doc-1"])
        self.assertEqual(a.text, "")
        self.assertIn('status="NOT READ"', attachment_turn_block([a]))

    def test_unknown_ids_are_dropped_and_the_order_is_kept(self):
        db = FakeDb([doc(1), doc(2)], objects={"doc-1.txt": TYPED.encode(), "doc-2.txt": TYPED.encode()})
        self.assertEqual([a.id for a in load_attachments(db, ["doc-2", "missing", "doc-1", "doc-2"])],
                         ["doc-2", "doc-1"])


if __name__ == "__main__":
    unittest.main()
