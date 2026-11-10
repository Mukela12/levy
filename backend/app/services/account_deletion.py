"""Delete a user's account and everything it owns.

The App Store (guideline 5.1.1(v)) and Google Play both require that people
who can make an account in the app can also delete it there, without having
to email anyone. The backend holds the service_role key, which bypasses row
level security, so every query here is filtered by the caller's id, or by ids
that were first read with that filter.

Order matters: children before parents, and the sign-in account last. If any
step fails nothing after it runs and the caller is told to try again; every
step is safe to repeat, so a retry finishes the job. Deleting the sign-in
account first would leave data behind that no one could find or remove.

A document the user owns that has been promoted to the shared library
(is_global) is not deleted with them: it is kept and its owner cleared, so
deleting an administrator's account can never take Acts out of the library.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("levy.account")

BATCH = 100


@dataclass
class DeletionReport:
    chats: int = 0
    messages: int = 0
    documents: int = 0
    library_documents_kept: int = 0
    artifacts: int = 0
    templates: int = 0
    matters: int = 0
    files: int = 0
    file_errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "file_errors"} | {
            "file_errors": len(self.file_errors)
        }


def _chunks(items: list[str], size: int = BATCH):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _ids(db, table: str, col: str, uid: str, cols: str = "id") -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        res = db.table(table).select(cols).eq(col, uid).range(start, start + 999).execute()
        page = res.data or []
        rows.extend(page)
        if len(page) < 1000:
            return rows
        start += 1000


def _storage_key(path: str | None) -> tuple[str, str] | None:
    """'bucket/key/with/slashes' -> ('bucket', 'key/with/slashes')."""
    if not path or "/" not in path or path.endswith("/pending"):
        return None
    bucket, _, key = path.partition("/")
    return (bucket, key) if bucket and key else None


def _remove_files(db, paths: dict[str, list[str]], report: DeletionReport) -> None:
    # A missing file is not a reason to keep someone's account; note it and go on.
    for bucket, keys in paths.items():
        for batch in _chunks(keys):
            try:
                db.storage.from_(bucket).remove(batch)
                report.files += len(batch)
            except Exception as e:  # noqa: BLE001
                report.file_errors.append(f"{bucket}: {e}")


def delete_account(db, uid: str) -> DeletionReport:
    """Remove everything `uid` owns, then the sign-in account itself."""
    if not uid or len(uid) < 32:
        raise ValueError("a user id is required")
    report = DeletionReport()
    files: dict[str, list[str]] = {}

    def add_file(path: str | None) -> None:
        key = _storage_key(path)
        if key:
            files.setdefault(key[0], []).append(key[1])

    sessions = [r["id"] for r in _ids(db, "chat_sessions", "user_id", uid)]
    docs = _ids(db, "legal_documents", "owner_id", uid, "id, is_global, pdf_storage_path")
    own_docs = [d for d in docs if not d.get("is_global")]
    library_docs = [d["id"] for d in docs if d.get("is_global")]
    doc_ids = [d["id"] for d in own_docs]
    artifacts = _ids(db, "artifacts", "owner_id", uid, "id, storage_path")
    templates = _ids(db, "templates", "owner_id", uid, "id, storage_path")

    # Feedback the user gave, and any left on their chats.
    db.table("message_feedback").delete().eq("user_id", uid).execute()
    for batch in _chunks(sessions):
        db.table("message_feedback").delete().in_("session_id", batch).execute()

    # Generated files (drafts, PDFs) and their rows.
    for a in artifacts:
        add_file(a.get("storage_path"))
    db.table("artifacts").delete().eq("owner_id", uid).execute()
    for batch in _chunks(sessions):
        db.table("artifacts").delete().in_("session_id", batch).execute()
    report.artifacts = len(artifacts)

    # Chats: document links, messages, then the chats.
    for batch in _chunks(sessions):
        db.table("chat_session_documents").delete().in_("session_id", batch).execute()
    for sid in sessions:
        res = db.table("chat_messages").delete().eq("session_id", sid).execute()
        report.messages += len(res.data or [])
    db.table("chat_sessions").delete().eq("user_id", uid).execute()
    report.chats = len(sessions)

    # Uploaded documents: links from any chat, search rows, then the document.
    for batch in _chunks(doc_ids):
        db.table("chat_session_documents").delete().in_("document_id", batch).execute()
    for d in own_docs:
        did = d["id"]
        db.table("legal_chunk_lexemes").delete().eq("document_id", did).execute()
        db.table("legal_chunks").delete().eq("document_id", did).execute()
        db.table("legal_hierarchy").delete().eq("document_id", did).execute()
        db.table("legal_documents").delete().eq("id", did).eq("owner_id", uid).execute()
        add_file(d.get("pdf_storage_path"))
        files.setdefault("legal-docs", []).extend([f"{did}.pdf", f"{did}.txt"])
    report.documents = len(own_docs)
    for did in library_docs:
        db.table("legal_documents").update({"owner_id": None}).eq("id", did).eq("owner_id", uid).execute()
    report.library_documents_kept = len(library_docs)
    db.table("document_folders").delete().eq("owner_id", uid).execute()

    # Templates and their folders.
    for t in templates:
        add_file(t.get("storage_path"))
    db.table("templates").delete().eq("owner_id", uid).execute()
    db.table("template_folders").delete().eq("owner_id", uid).execute()
    report.templates = len(templates)

    # Matters last among the data: chats pointed at them.
    matters = _ids(db, "matters", "owner_id", uid)
    db.table("matters").delete().eq("owner_id", uid).execute()
    report.matters = len(matters)

    for bucket in files:
        files[bucket] = sorted(set(files[bucket]))
    _remove_files(db, files, report)

    # The sign-in account: its email, password hash and profile go with it.
    db.auth.admin.delete_user(uid)
    logger.info("account deleted: %s… %s", uid[:8], report.as_dict())
    return report
