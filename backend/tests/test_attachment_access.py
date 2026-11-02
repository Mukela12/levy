"""Who may put a document in front of the model, and what a chunked upload
stores.

An attachment's text now goes to the model whole, so a client-supplied id for
someone else's upload must not get through. A chunked upload was created
public (the column default) and patched private afterwards, kept the Act
parser's title, no page count and no text file; on 23 October 2026 its chunks
held 9,300 of the PDF's 15,400 characters.
"""
import io
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

import pymupdf  # noqa: E402
from fastapi import UploadFile  # noqa: E402

from app.routes import api  # noqa: E402
from app.services import pdf_tools  # noqa: E402
from app.services.attachments import MAX_ATTACHMENTS  # noqa: E402

ME, THEM = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
MINE = "aaaaaaaa-0000-0000-0000-000000000001"
THEIRS = "aaaaaaaa-0000-0000-0000-000000000002"
LIBRARY = "aaaaaaaa-0000-0000-0000-000000000003"
UNOWNED = "aaaaaaaa-0000-0000-0000-000000000004"   # an admin-ingested form: private, no owner

DOCS = [
    {"id": MINE, "owner_id": ME, "is_global": False},
    {"id": THEIRS, "owner_id": THEM, "is_global": False},
    {"id": LIBRARY, "owner_id": None, "is_global": True},
    {"id": UNOWNED, "owner_id": None, "is_global": False},
]


class Query:
    def __init__(self, db, name):
        self.db, self.name, self.rows, self.patch = db, name, list(db.tables.get(name, [])), None

    def select(self, *_):
        return self

    def in_(self, col, values):
        self.rows = [r for r in self.rows if r.get(col) in values]
        return self

    def eq(self, col, value):
        self.rows = [r for r in self.rows if r.get(col) == value]
        return self

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    def update(self, patch):
        self.patch = patch
        return self

    def execute(self):
        if self.db.fail:
            raise RuntimeError("statement timeout")
        if self.patch is not None:
            self.db.updates.append(self.patch)
        return types.SimpleNamespace(data=self.rows)


class Db:
    def __init__(self, docs=(), fail=False):
        self.tables = {"legal_documents": list(docs)}
        self.fail = fail
        self.updates: list[dict] = []
        self.uploads: dict[str, bytes] = {}
        bucket = types.SimpleNamespace(upload=self._upload)
        self.storage = types.SimpleNamespace(from_=lambda name: bucket)

    def _upload(self, path, file, file_options=None):
        self.uploads[path] = file

    def table(self, name):
        return Query(self, name)


class UsableIds(unittest.TestCase):
    def check(self, ids, uid=ME, db=None):
        with patch.object(api, "get_db", lambda: db or Db(DOCS)):
            return api._usable_doc_ids(ids, uid)

    def test_own_and_library_documents_pass_and_others_do_not(self):
        self.assertEqual(self.check([THEIRS, MINE, LIBRARY, UNOWNED]), [MINE, LIBRARY])

    def test_a_guest_gets_library_documents_only(self):
        self.assertEqual(self.check([MINE, LIBRARY], uid=None), [LIBRARY])

    def test_no_list_stays_no_list(self):
        # None tells the agent to read the session's own attachment list.
        self.assertIsNone(self.check(None))
        self.assertEqual(self.check([]), [])

    def test_junk_and_repeats_are_dropped_and_the_count_is_capped(self):
        self.assertEqual(self.check(["not-a-uuid", MINE, MINE, 7]), [MINE])
        many = [f"bbbbbbbb-0000-0000-0000-{i:012d}" for i in range(MAX_ATTACHMENTS + 5)]
        rows = [{"id": d, "owner_id": ME, "is_global": False} for d in many]
        self.assertEqual(len(self.check(many, db=Db(rows))), MAX_ATTACHMENTS)

    def test_a_failed_check_passes_nothing(self):
        self.assertEqual(self.check([MINE], db=Db(DOCS, fail=True)), [])


class ReadPdfPages(unittest.IsolatedAsyncioTestCase):
    async def test_someone_elses_upload_is_refused_before_it_is_downloaded(self):
        downloads = []

        def download(doc_id):
            downloads.append(doc_id)
            raise RuntimeError("no stored PDF")
        with patch.object(pdf_tools, "get_db", lambda: Db(DOCS)), \
                patch.object(pdf_tools, "_download_corpus_pdf", download), \
                patch.object(pdf_tools, "_library_text_read", lambda *a, **k: {"result": {"pages": []}}):
            refused = await pdf_tools.read_pdf_pages(document_id=THEIRS, owner_id=ME)
            self.assertIn("belongs to another user", refused["result"]["error"])
            self.assertEqual(downloads, [])
            for allowed in (MINE, LIBRARY, UNOWNED):
                out = await pdf_tools.read_pdf_pages(document_id=allowed, owner_id=ME)
                self.assertNotIn("error", out["result"])
            self.assertEqual(downloads, [MINE, LIBRARY, UNOWNED])


def six_page_pdf() -> bytes:
    doc = pymupdf.open()
    for n in range(1, 7):
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 800),
                            f"Page {n}. " + "The employee worked overtime on rest days. " * 25, fontsize=9)
    return doc.tobytes()


class ChunkedUpload(unittest.IsolatedAsyncioTestCase):
    async def test_a_six_page_upload_is_private_from_the_start_and_keeps_its_text(self):
        db = Db()
        seen = {}

        def ingest(path, doc_fields=None, **kw):
            seen["doc_fields"] = doc_fields
            return {"status": "success", "document": {"id": "doc-new"}, "chunks_created": 5}
        pdf = six_page_pdf()
        with patch("app.db.supabase.get_db", lambda: db), patch.object(api, "ingest_pdf", ingest):
            res = await api.upload_document(file=UploadFile(file=io.BytesIO(pdf), filename="Overtime claim.pdf"),
                                            user_id=None, folder_id=None, uid=ME)
        fields = seen["doc_fields"]
        self.assertEqual((fields["is_global"], fields["owner_id"]), (False, ME))
        self.assertEqual((fields["title"], fields["short_name"]), ("Overtime claim", "Overtime claim"))
        self.assertEqual((fields["pdf_page_count"], fields["pdf_size_bytes"]), (6, len(pdf)))
        self.assertEqual((res["tier"], res["page_count"]), ("rag", 6))
        text = db.uploads["doc-new.txt"].decode()
        self.assertIn("Page 1.", text)
        self.assertIn("Page 6.", text)
        self.assertIn("doc-new.pdf", db.uploads)
        self.assertFalse(any("is_global" in u for u in db.updates))   # no public window to patch shut


if __name__ == "__main__":
    unittest.main()
