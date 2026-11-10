"""Deleting an account removes everything that person owns and nothing else.

The backend uses the service_role key, which ignores row level security, so a
missing filter here would delete other people's chats. These tests run the
deletion against an in-memory copy of the tables holding two users' data and
a shared library, then check what is left.
"""
import sys
import types
import unittest

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from fastapi import HTTPException  # noqa: E402

from app.services.account_deletion import delete_account  # noqa: E402

ME = "11111111-1111-1111-1111-111111111111"
THEM = "22222222-2222-2222-2222-222222222222"


class Result:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, db, name):
        self.db, self.name, self.filters, self.op, self.patch = db, name, [], "select", None
        self.window = None

    def select(self, *_):
        self.op = "select"
        return self

    def delete(self):
        self.op = "delete"
        return self

    def update(self, patch):
        self.op, self.patch = "update", patch
        return self

    def eq(self, col, value):
        self.filters.append(lambda r, c=col, v=value: r.get(c) == v)
        return self

    def in_(self, col, values):
        self.filters.append(lambda r, c=col, v=tuple(values): r.get(c) in v)
        return self

    def range(self, start, end):
        self.window = (start, end)
        return self

    def execute(self):
        if not self.filters and self.op != "select":
            raise AssertionError(f"unfiltered {self.op} on {self.name}")
        rows = self.db.tables.setdefault(self.name, [])
        hit = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "delete":
            self.db.tables[self.name] = [r for r in rows if r not in hit]
        elif self.op == "update":
            for r in hit:
                r.update(self.patch)
        elif self.window:
            hit = hit[self.window[0] : self.window[1] + 1]
        return Result([dict(r) for r in hit])


class Bucket:
    def __init__(self, db, name):
        self.db, self.name = db, name

    def remove(self, keys):
        self.db.removed.setdefault(self.name, []).extend(keys)


class Storage:
    def __init__(self, db):
        self.db = db

    def from_(self, name):
        return Bucket(self.db, name)


class Admin:
    def __init__(self, db):
        self.db = db

    def delete_user(self, uid):
        self.db.deleted_users.append(uid)


class FakeDB:
    def __init__(self, tables):
        self.tables = tables
        self.removed: dict[str, list[str]] = {}
        self.deleted_users: list[str] = []
        self.storage = Storage(self)
        self.auth = types.SimpleNamespace(admin=Admin(self))

    def table(self, name):
        return Query(self, name)


def world():
    return FakeDB({
        "chat_sessions": [
            {"id": "s-me", "user_id": ME, "matter_id": "m-me"},
            {"id": "s-them", "user_id": THEM, "matter_id": None},
        ],
        "chat_messages": [
            {"id": "msg-me-1", "session_id": "s-me"},
            {"id": "msg-me-2", "session_id": "s-me"},
            {"id": "msg-them", "session_id": "s-them"},
        ],
        "message_feedback": [
            {"id": "f-me", "user_id": ME, "session_id": "s-me", "message_id": "msg-me-2"},
            {"id": "f-them", "user_id": THEM, "session_id": "s-them", "message_id": "msg-them"},
        ],
        "chat_session_documents": [
            {"session_id": "s-me", "document_id": "d-lib"},
            # Someone else's chat that attached my upload: the link goes with the upload.
            {"session_id": "s-them", "document_id": "d-me"},
            {"session_id": "s-them", "document_id": "d-them"},
        ],
        "legal_documents": [
            {"id": "d-me", "owner_id": ME, "is_global": False, "pdf_storage_path": "legal-docs/d-me.pdf"},
            {"id": "d-them", "owner_id": THEM, "is_global": False, "pdf_storage_path": "legal-docs/d-them.pdf"},
            {"id": "d-lib", "owner_id": None, "is_global": True},
            # An Act I uploaded as an administrator: it stays in the library.
            {"id": "d-my-act", "owner_id": ME, "is_global": True},
        ],
        "legal_chunks": [
            {"id": "c-me", "document_id": "d-me"},
            {"id": "c-them", "document_id": "d-them"},
            {"id": "c-act", "document_id": "d-my-act"},
        ],
        "legal_chunk_lexemes": [
            {"chunk_id": "c-me", "document_id": "d-me"},
            {"chunk_id": "c-act", "document_id": "d-my-act"},
        ],
        "legal_hierarchy": [{"id": "h-act", "document_id": "d-my-act"}],
        "document_folders": [{"id": "fo-me", "owner_id": ME}, {"id": "fo-them", "owner_id": THEM}],
        "artifacts": [
            {"id": "a-me", "owner_id": ME, "session_id": "s-me", "storage_path": "artifacts/me/draft.pdf"},
            {"id": "a-them", "owner_id": THEM, "session_id": "s-them", "storage_path": "artifacts/them/x.pdf"},
        ],
        "templates": [
            {"id": "t-me", "owner_id": ME, "storage_path": f"templates/{ME}/t.docx"},
            {"id": "t-them", "owner_id": THEM, "storage_path": f"templates/{THEM}/t.docx"},
        ],
        "template_folders": [{"id": "tf-me", "owner_id": ME}, {"id": "tf-them", "owner_id": THEM}],
        "matters": [{"id": "m-me", "owner_id": ME}, {"id": "m-them", "owner_id": THEM}],
    })


def ids(db, table):
    return sorted(r.get("id") or f"{r.get('session_id')}:{r.get('document_id')}" for r in db.tables.get(table, []))


class DeleteAccountTest(unittest.TestCase):
    def test_removes_everything_i_own(self):
        db = world()
        report = delete_account(db, ME)
        self.assertEqual(ids(db, "chat_sessions"), ["s-them"])
        self.assertEqual(ids(db, "chat_messages"), ["msg-them"])
        self.assertEqual(ids(db, "message_feedback"), ["f-them"])
        self.assertEqual(ids(db, "artifacts"), ["a-them"])
        self.assertEqual(ids(db, "templates"), ["t-them"])
        self.assertEqual(ids(db, "template_folders"), ["tf-them"])
        self.assertEqual(ids(db, "matters"), ["m-them"])
        self.assertEqual(ids(db, "document_folders"), ["fo-them"])
        self.assertEqual(ids(db, "legal_chunks"), ["c-act", "c-them"])
        self.assertEqual(db.deleted_users, [ME])
        self.assertEqual(report.chats, 1)
        self.assertEqual(report.documents, 1)

    def test_leaves_other_people_alone(self):
        db = world()
        delete_account(db, ME)
        self.assertIn("d-them", ids(db, "legal_documents"))
        self.assertEqual(ids(db, "chat_session_documents"), ["s-them:d-them"])
        self.assertNotIn(THEM, db.deleted_users)
        for bucket, keys in db.removed.items():
            self.assertFalse([k for k in keys if "them" in k or THEM in k], bucket)

    def test_library_documents_stay_with_no_owner(self):
        db = world()
        report = delete_account(db, ME)
        act = next(d for d in db.tables["legal_documents"] if d["id"] == "d-my-act")
        self.assertIsNone(act["owner_id"])
        self.assertTrue(act["is_global"])
        self.assertIn("c-act", ids(db, "legal_chunks"))
        self.assertEqual(len(db.tables["legal_hierarchy"]), 1)
        self.assertEqual(report.library_documents_kept, 1)
        self.assertIn("d-lib", ids(db, "legal_documents"))

    def test_removes_my_files(self):
        db = world()
        delete_account(db, ME)
        self.assertEqual(sorted(db.removed["legal-docs"]), ["d-me.pdf", "d-me.txt"])
        self.assertEqual(db.removed["artifacts"], ["me/draft.pdf"])
        self.assertEqual(db.removed["templates"], [f"{ME}/t.docx"])

    def test_sign_in_account_goes_last(self):
        db = world()
        order = []
        original_table = db.table

        def table(name):
            order.append(name)
            return original_table(name)

        db.table = table
        db.auth.admin.delete_user = lambda uid: order.append("auth")
        delete_account(db, ME)
        self.assertEqual(order[-1], "auth")

    def test_a_failed_step_keeps_the_sign_in_account(self):
        db = world()
        original_table = db.table

        def table(name):
            if name == "legal_chunks":
                raise RuntimeError("statement timeout")
            return original_table(name)

        db.table = table
        with self.assertRaises(RuntimeError):
            delete_account(db, ME)
        self.assertEqual(db.deleted_users, [])
        # A retry once the database is healthy finishes the job.
        db.table = original_table
        delete_account(db, ME)
        self.assertEqual(db.deleted_users, [ME])
        self.assertEqual(ids(db, "chat_sessions"), ["s-them"])

    def test_needs_a_real_user_id(self):
        with self.assertRaises(ValueError):
            delete_account(world(), "")


class RouteTest(unittest.TestCase):
    def test_route_needs_the_confirm_word(self):
        from app.routes import api

        with self.assertRaises(HTTPException) as caught:
            api.delete_my_account(api.DeleteAccountRequest(confirm="yes"), uid=ME)
        self.assertEqual(caught.exception.status_code, 400)

    def test_route_deletes_with_the_confirm_word(self):
        from unittest.mock import patch

        from app.routes import api

        db = world()
        with patch.object(api, "get_db", return_value=db):
            out = api.delete_my_account(api.DeleteAccountRequest(confirm="Delete"), uid=ME)
        self.assertEqual(out["status"], "deleted")
        self.assertEqual(db.deleted_users, [ME])


if __name__ == "__main__":
    unittest.main()
