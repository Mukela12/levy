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
    # A logo. With the organisation's name and address typed into the
    # description, it is a letterhead (see letterhead_of).
    ".png": "png",
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".webp": "webp",
}
IMAGE_TYPES = frozenset({"png", "jpg", "webp"})
MAX_LOGO_BYTES = 4 * 1024 * 1024

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
    if file_type in IMAGE_TYPES:
        return "", None
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
    "png": "image/png",
    "jpg": "image/jpeg",
    "webp": "image/webp",
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


def get_template_by_id(owner_id: str, template_id: str) -> dict | None:
    """Fetch a single template owned by `owner_id` by its UUID.

    Returns None if not found OR not owned by the caller. The drafting
    tools use this to look up the template's name + preview text so they
    can render the firm's chambers letterhead into the artifact.
    """
    if not owner_id or not template_id:
        return None
    db = get_db()
    res = (
        db.table("templates")
        .select(
            "id, name, description, file_type, page_count, preview_text, storage_path"
        )
        .eq("owner_id", owner_id)
        .eq("id", template_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def _created_ts(row: dict) -> float:
    raw = row.get("created_at") or ""
    try:
        from datetime import datetime

        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return 0.0


# ─── Letterheads ─────────────────────────────────────────────────────────────
#
# A template can carry a letterhead three ways: a Word file whose header holds
# the organisation's logo and details, a logo image with the details typed
# into the description, or (the original) a text template whose opening lines
# are the firm's name and address. letterhead_of reads whichever it is into
# one shape the PDF and Word renderers both print.

import re as _re
import time as _time

_LETTERHEAD_END = _re.compile(
    r"\[[^\]]*\]|\{\{|<<|_{4,}"
    r"|^(dear|to|re|ref|our ref|your ref|date|attention|attn|subject|yours|sincerely|regards)\b",
    _re.I,
)
_LH_CACHE: dict[str, tuple[float, dict | None]] = {}
_LH_TTL = 600.0


def header_lines(preview: str) -> list[str]:
    """The opening lines of a text template that are its letterhead.

    Most templates are whole letter skeletons, and copying their "[DATE] /
    Dear Sir / [BODY]" lines put an empty letter on top of every draft, so the
    block stops at the first line that belongs to the letter itself.
    """
    out: list[str] = []
    for ln in (ln.strip() for ln in (preview or "").splitlines()):
        if not ln:
            continue
        if _LETTERHEAD_END.search(ln) or len(ln) > 90 or len(out) == 8:
            break
        out.append(ln)
    return out


def download_template(template: dict) -> bytes | None:
    path = (template or {}).get("storage_path") or ""
    bucket, _, key = path.partition("/")
    if not bucket or not key:
        return None
    try:
        return get_db().storage.from_(bucket).download(key)
    except Exception:  # noqa: BLE001
        return None


def normalise_logo(data: bytes) -> tuple[bytes, str] | None:
    """A logo as a modest PNG the PDF and Word renderers can both place.

    Returns None for anything Pillow cannot open (a Windows metafile inside a
    Word header, a broken upload): no logo is better than a failed document.
    """
    if not data or len(data) > MAX_LOGO_BYTES:
        return None
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im.load()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        im.thumbnail((900, 420))
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        return buf.getvalue(), "image/png"
    except Exception:  # noqa: BLE001
        return None


def _docx_letterhead(data: bytes) -> tuple[list[str], bytes | None]:
    """Header text and the first logo of a Word template."""
    from docx import Document
    doc = Document(io.BytesIO(data))
    lines: list[str] = []
    logo: bytes | None = None
    for section in doc.sections[:1]:
        for hdr in (section.first_page_header, section.header):
            try:
                texts = [p.text.strip() for p in hdr.paragraphs]
                for tbl in hdr.tables:
                    for row in tbl.rows:
                        for cell in row.cells:
                            texts += [p.text.strip() for p in cell.paragraphs]
                for t in texts:
                    if t and t not in lines:
                        lines.append(t)
                if logo is None:
                    for rel in hdr.part.rels.values():
                        if "image" in rel.reltype and not rel.is_external:
                            logo = rel.target_part.blob
                            break
            except Exception:  # noqa: BLE001
                continue
    if logo is None:
        # No header image: a logo placed at the very top of the page instead.
        try:
            for para in doc.paragraphs[:6]:
                ids = _re.findall(r'r:embed="([^"]+)"', para._p.xml)
                if ids:
                    logo = doc.part.related_parts[ids[0]].blob
                    break
        except Exception:  # noqa: BLE001
            logo = None
    if not lines:
        lines = header_lines("\n".join(p.text for p in doc.paragraphs[:12]))
    return lines[:8], logo


def letterhead_of(owner_id: str | None, template_id: str | None) -> dict | None:
    """The letterhead a template carries, or None when it carries none.

    {"lines": [...], "logo": bytes | None, "logo_mime": str | None,
     "docx": bytes | None}. `docx` is the Word template itself, so a Word
    export can be built inside the user's own file, header and footer intact.
    """
    if not owner_id or not template_id:
        return None
    key = f"{owner_id}:{template_id}"
    hit = _LH_CACHE.get(key)
    if hit and _time.time() - hit[0] < _LH_TTL:
        return hit[1]
    out: dict | None = None
    try:
        tpl = get_template_by_id(owner_id, template_id)
        if tpl:
            kind = tpl.get("file_type")
            lines: list[str] = []
            logo_raw: bytes | None = None
            docx_bytes: bytes | None = None
            if kind in IMAGE_TYPES:
                logo_raw = download_template(tpl)
                desc = (tpl.get("description") or "").strip()
                lines = [ln.strip() for ln in _re.split(r"\n|\s\|\s|\s·\s", desc) if ln.strip()][:8]
            elif kind == "docx":
                docx_bytes = download_template(tpl)
                if docx_bytes:
                    lines, logo_raw = _docx_letterhead(docx_bytes)
                else:
                    lines = header_lines(tpl.get("preview_text") or "")
            else:
                lines = header_lines(tpl.get("preview_text") or "")
            logo = normalise_logo(logo_raw) if logo_raw else None
            if lines or logo:
                out = {"lines": lines, "logo": logo[0] if logo else None, "logo_mime": logo[1] if logo else None,
                       "docx": docx_bytes, "template_id": template_id, "name": tpl.get("name")}
    except Exception:  # noqa: BLE001 — a letterhead must never fail a draft
        out = None
    _LH_CACHE[key] = (_time.time(), out)
    return out


def forget_letterhead(owner_id: str, template_id: str) -> None:
    _LH_CACHE.pop(f"{owner_id}:{template_id}", None)


def save_logo_template(owner_id: str, name: str, logo: bytes, lines: list[str]) -> dict:
    """Store a logo and its organisation details as a letterhead template."""
    png = normalise_logo(logo)
    if not png:
        raise ValueError("that image could not be read as a logo")
    storage_path = upload_to_storage(png[0], "png", owner_id)
    db = get_db()
    base = (name or "Letterhead").strip()[:80] or "Letterhead"
    row = None
    for attempt in range(4):   # names are unique per owner
        try:
            row = db.table("templates").insert({
                "owner_id": owner_id, "name": base if attempt == 0 else f"{base} ({attempt + 1})",
                "description": "\n".join(ln.strip() for ln in lines if ln and ln.strip())[:600] or None,
                "file_type": "png", "file_size_bytes": len(png[0]), "storage_path": storage_path,
                "preview_text": None, "page_count": None,
            }).execute().data[0]
            break
        except Exception:  # noqa: BLE001
            continue
    if not row:
        raise ValueError("the letterhead could not be saved")
    return row
