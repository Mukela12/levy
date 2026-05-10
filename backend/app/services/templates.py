"""
Templates service.

Templates are user-owned reusable document skeletons (.docx, .pdf, .txt, .md)
the user uploads from /templates and the agent can later suggest + use to
draft new documents inside the chat.

This module is responsible for:
  - Extracting a short text preview from the uploaded file at upload time so
    `suggest_templates` can rank without re-fetching binary content.
  - Producing the canonical storage path (bucket+key) the API layer writes to
    Supabase Storage.
"""

from __future__ import annotations

import io
import os
import uuid
from typing import Tuple

from ..db.supabase import get_db


SUPPORTED_TYPES: dict[str, str] = {
    ".docx": "docx",
    ".pdf": "pdf",
    ".txt": "txt",
    ".md": "md",
}

PREVIEW_MAX_CHARS = 2000
TEMPLATES_BUCKET = "templates"


def file_type_for(filename: str) -> str | None:
    ext = os.path.splitext(filename or "")[1].lower()
    return SUPPORTED_TYPES.get(ext)


def extract_preview(content: bytes, file_type: str) -> Tuple[str, int | None]:
    """
    Return (preview_text, page_count) for the given file bytes.

    Page count is best-effort; None when not applicable (txt/md) or extraction
    fails. We swallow extraction errors deliberately — a missing preview must
    never block a template upload.
    """
    if file_type == "txt" or file_type == "md":
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            text = ""
        return text[:PREVIEW_MAX_CHARS], None

    if file_type == "pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            pages = len(reader.pages)
            buf: list[str] = []
            char_count = 0
            for page in reader.pages:
                page_text = page.extract_text() or ""
                buf.append(page_text)
                char_count += len(page_text)
                if char_count >= PREVIEW_MAX_CHARS:
                    break
            return ("\n".join(buf))[:PREVIEW_MAX_CHARS], pages
        except Exception:  # noqa: BLE001
            return "", None

    if file_type == "docx":
        try:
            from docx import Document

            doc = Document(io.BytesIO(content))
            paragraphs = [p.text for p in doc.paragraphs if p.text]
            text = "\n".join(paragraphs)
            return text[:PREVIEW_MAX_CHARS], None
        except Exception:  # noqa: BLE001
            return "", None

    return "", None


def upload_to_storage(content: bytes, file_type: str, owner_id: str) -> str:
    """
    Upload bytes to the `templates` Supabase Storage bucket and return the
    full storage path ('templates/<key>').

    Bucket creation is part of the migration. Errors propagate.
    """
    db = get_db()
    key = f"{owner_id}/{uuid.uuid4().hex}.{file_type}"
    db.storage.from_(TEMPLATES_BUCKET).upload(
        path=key,
        file=content,
        file_options={
            "content-type": _CONTENT_TYPES[file_type],
            "upsert": "false",
        },
    )
    return f"{TEMPLATES_BUCKET}/{key}"


_CONTENT_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "md": "text/markdown",
}


def list_templates_for_owner(
    owner_id: str,
    folder_id: str | None = None,
) -> list[dict]:
    """Return the owner's templates, optionally filtered to one folder.

    `folder_id` semantics:
      - None        : every template (used for the suggest_templates ranker
                      so all of the user's templates can match).
      - "unfiled"   : templates with folder_id IS NULL.
      - any UUID    : templates inside that folder.
    """
    db = get_db()
    q = (
        db.table("templates")
        .select(
            "id, name, description, file_type, file_size_bytes, page_count, "
            "preview_text, folder_id, created_at, updated_at"
        )
        .eq("owner_id", owner_id)
        .order("created_at", desc=True)
    )
    if folder_id == "unfiled":
        q = q.is_("folder_id", "null")
    elif folder_id:
        q = q.eq("folder_id", folder_id)
    return q.execute().data or []


def suggest_templates_for(owner_id: str, query: str | None) -> list[dict]:
    """
    Return up to 3 templates most relevant to `query`, scored by simple
    keyword overlap against name + description + preview_text.

    If the user has 3 or fewer templates, return all of them. If `query` is
    empty, return the most recently created.
    """
    rows = list_templates_for_owner(owner_id)
    if not rows:
        return []
    if len(rows) <= 3 and not query:
        return rows[:3]

    if not query:
        return rows[:3]

    qwords = {w for w in query.lower().split() if len(w) > 2}
    if not qwords:
        return rows[:3]

    scored: list[tuple[int, dict]] = []
    for r in rows:
        haystack = " ".join(
            [
                r.get("name") or "",
                r.get("description") or "",
                (r.get("preview_text") or "")[:1000],
            ]
        ).lower()
        score = sum(1 for w in qwords if w in haystack)
        scored.append((score, r))

    scored.sort(key=lambda x: (-x[0], -_created_ts(x[1])))
    top = [r for s, r in scored if s > 0][:3]
    if not top:
        # Nothing matched — surface the most recent so the user still sees
        # what's in their library.
        top = rows[:3]
    return top


def _created_ts(row: dict) -> float:
    raw = row.get("created_at") or ""
    try:
        from datetime import datetime

        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return 0.0
