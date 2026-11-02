"""What the model is told about the documents a user attached to a chat.

Twice a user attached a document whose text never reached the model, and the
answer admitted it only later ("flagged but the text content has not come
through"). Small attachments were listed as "inline" whether or not any text
had loaded: a scan has no text layer, and a document past the per-turn budget
was dropped silently. Each attachment now carries an honest status, and an
unread one comes with the way to read it.

On 23 October 2026 a reply said nothing had been attached when a six-page PDF
had. The note about it was the last 557 characters of a 73,000-character
system prompt, a million characters of conversation before a question that
never said "attached", and it read only "searchable: use search_corpus". The
model made no tool call. A search could not have shown it the document anyway:
the Act parser had kept 9,300 of the PDF's 15,400 characters. Attachments now
travel in the user's own turn, in front of the question, with their text: the
text file stored at upload, else the PDF's own text for the user's upload,
else the search index's chunks for a library document.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

INLINE_MAX_CHARS = 30_000   # per attachment
INLINE_TOTAL_CAP = 60_000   # across all attachments in one turn
MAX_ATTACHMENTS = 10        # document ids honoured per request


IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff")


def image_to_pdf(content: bytes, filename: str) -> bytes:
    """A photo or screenshot as a one-page PDF.

    Most users are on phones and photograph the document (a payslip, a court
    notice, a table of tax bands), but chat attachments took only PDFs. As a
    one-page PDF with no text layer the photo follows the scanned-PDF path:
    the upload reports needs_ocr, and read_pdf_pages hands the page to the
    model as an image, which it reads. Raises ValueError for a file PyMuPDF
    cannot open as an image (HEIC among them).
    """
    import pymupdf
    ext = filename.rsplit(".", 1)[-1].lower()
    kind = {"jpg": "jpeg", "tif": "tiff"}.get(ext, ext)
    try:
        img = pymupdf.open(stream=content, filetype=kind)
        pdf = img.convert_to_pdf()
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"not a readable {ext} image") from e
    if not pdf or pymupdf.open(stream=pdf, filetype="pdf").page_count < 1:
        raise ValueError("image produced an empty PDF")
    return pdf


def looks_scanned(text: str | None, page_count: int | None) -> bool:
    """Too little text for its pages: a scan, a photo, or a PDF of images.

    A typed page carries well over a thousand characters; under 80 a page is a
    header or a stamp at most.
    """
    return len((text or "").strip()) < 80 * max(1, page_count or 1)


def extract_pdf_text(content: bytes, max_chars: int | None = None) -> tuple[str, bool, int, int]:
    """A PDF's text, page by page, read the way the corpus is read.

    Stops after the page that takes it past `max_chars`, so a long upload costs
    only the pages the model will be shown. Returns (text, complete,
    pages_read, page_count).
    """
    import pdfplumber

    from .parser import page_text

    parts: list[str] = []
    total = 0
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            parts.append(page_text(page) or "")
            total += len(parts[-1]) + 2
            if max_chars is not None and total > max_chars:
                break
    return "\n\n".join(parts).strip(), len(parts) == page_count, len(parts), page_count


@dataclass
class Attachment:
    """One attached document, as the model will be shown it."""
    id: str
    name: str
    pages: int | None = None
    text: str = ""          # at most INLINE_MAX_CHARS; empty when nothing could be read
    complete: bool = False  # `text` is the whole document
    source: str = "none"    # "stored" text file, the "pdf" itself, the search "index", or "none"


def _read(db, row: dict, a: Attachment) -> None:
    """Fill in `a.text` from the best source this document has."""
    # 1. The text file written at upload (every upload since 2 November 2026,
    #    and small ones before that).
    try:
        blob = db.storage.from_("legal-docs").download(f"{a.id}.txt")
        text = bytes(blob).decode("utf-8", errors="ignore").strip() if blob else ""
    except Exception:  # noqa: BLE001 — no text file: try the next source
        text = ""
    if text:
        if not looks_scanned(text, a.pages):
            a.text, a.complete, a.source = text[:INLINE_MAX_CHARS], len(text) <= INLINE_MAX_CHARS, "stored"
        return
    # 2. The user's own upload without one: its PDF. Its chunks are no
    #    substitute, since the Act parser drops whatever is not a section.
    path = row.get("pdf_storage_path") or ""
    if row.get("owner_id") and "/" in path:
        try:
            bucket, _, key = path.partition("/")
            text, complete, read, count = extract_pdf_text(bytes(db.storage.from_(bucket).download(key)),
                                                           INLINE_MAX_CHARS)
        except Exception:  # noqa: BLE001 — unreadable or missing: fall back to the index
            text, complete, read, count = "", False, 0, 0
        if count:
            a.pages = a.pages or count
            if not looks_scanned(text, read):
                a.text, a.source = text[:INLINE_MAX_CHARS], "pdf"
                a.complete = complete and len(text) <= INLINE_MAX_CHARS
            return
    # 3. A library document: its chunks, in order.
    if (row.get("total_chunks") or 0) > 0:
        try:
            chunks = (db.table("legal_chunks").select("content").eq("document_id", a.id)
                      .order("chunk_index").limit(60).execute().data or [])
        except Exception:  # noqa: BLE001
            chunks = []
        text = "\n\n".join((c.get("content") or "").strip() for c in chunks).strip()
        if text:
            a.text, a.source = text[:INLINE_MAX_CHARS], "index"
            a.complete = len(text) <= INLINE_MAX_CHARS and len(chunks) >= (row.get("total_chunks") or 0)


def load_attachments(db, doc_ids: list[str]) -> list[Attachment]:
    """The attached documents, in the order given, each with what could be read.

    Ids that match no document are left out. Blocking I/O: run it off the event
    loop.
    """
    ids = list(dict.fromkeys(doc_ids or []))[:MAX_ATTACHMENTS]
    if not ids:
        return []
    rows = (db.table("legal_documents")
            .select("id,title,short_name,pdf_page_count,total_chunks,pdf_storage_path,owner_id")
            .in_("id", ids).execute().data or [])
    by_id = {r["id"]: r for r in rows}
    out: list[Attachment] = []
    for doc_id in ids:
        row = by_id.get(doc_id)
        if not row:
            continue
        a = Attachment(id=doc_id, name=(row.get("short_name") or row.get("title") or "untitled").strip(),
                       pages=row.get("pdf_page_count"))
        _read(db, row, a)
        out.append(a)
    return out


_UNREAD_RULE = (
    "SOME ATTACHMENTS HAVE NOT BEEN READ (status NOT READ or NOT INCLUDED). Before you say "
    "anything about their contents, read them with `read_pdf_pages` and the document_id shown: "
    "pages with no text come back as images you can read, at most 6 pages per call. If a file "
    "still cannot be read, say so plainly at the START of your answer and ask the user to paste "
    "the part that matters or send a clearer copy. Never describe, summarise or rely on a "
    "document you have not read."
)


def attachment_turn_block(current: list[Attachment], earlier: list[Attachment] | None = None) -> str:
    """The attachments, written into the user's turn in front of the question.

    `current` were attached to this message and are read first. `earlier` were
    attached to a recent message and are repeated so a follow-up ("I attached a
    PDF", "what does clause 4 say?") is answered from the document itself.
    Current attachments get the space first; INLINE_TOTAL_CAP covers both.
    """
    seen = {a.id for a in current}
    earlier = [a for a in (earlier or []) if a.id not in seen]
    if not current and not earlier:
        return ""
    used = 0
    unread = False

    def render(a: Attachment) -> str:
        nonlocal used, unread
        name = " ".join(a.name.replace('"', "'").split()) or "untitled"
        attrs = f'name="{name}" document_id="{a.id}"' + (f' pages="{a.pages}"' if a.pages else "")
        if not a.text:
            unread = True
            return (f'<document {attrs} status="NOT READ">No text could be read from it: probably a '
                    "scan or a photo. Read it with read_pdf_pages and this document_id before you "
                    "say anything about it.</document>")
        room = INLINE_TOTAL_CAP - used
        if room <= 0:
            unread = True
            return (f'<document {attrs} status="NOT INCLUDED">There is no room left for its text in '
                    "this turn. Read it with read_pdf_pages and this document_id.</document>")
        text = a.text[:room]
        used += len(text)
        cut = not a.complete or len(text) < len(a.text)
        notes = ""
        if cut:
            notes += ("\n[Cut here. Read the rest with read_pdf_pages (this document_id and a later "
                      "page_start), or search it with search_corpus.]")
        if a.source == "index":
            notes += ("\n[This is the library's search index of the document, which can leave parts "
                      "out. For exact wording, read the pages with read_pdf_pages.]")
        status = "opening only" if cut else "full text"
        return f'<document {attrs} status="{status}">\n{text}{notes}\n</document>'

    parts: list[str] = []
    if current:
        one = len(current) == 1
        head = (
            f"The user attached {'this document' if one else f'these {len(current)} documents'} to the "
            f"message below. Read {'it' if one else 'them'} before you answer: when the message says "
            "\"this\", \"the document\", \"the attachment\", \"the PDF\" or \"what I sent\", it means "
            f"{'this document' if one else 'these documents'}. {'It is' if one else 'They are'} "
            "attached, so never say that nothing was attached or pasted. Do not call gov_search, "
            "web_search or news_search until you have read the attachments, and cite them by name "
            "when you quote them."
        )
        body = "\n\n".join(render(a) for a in current)
        parts.append(f"<attachments>\n{head}\n\n{body}\n</attachments>")
    if earlier:
        one = len(earlier) == 1
        head = (
            f"Earlier in this chat the user attached {'this document' if one else 'these documents'} "
            f"to a message. {'Its' if one else 'Their'} text is repeated here so that follow-up "
            f"questions are answered from {'it' if one else 'them'}: use {'it' if one else 'them'} "
            "whenever the message below refers to an attachment, and never say that nothing was "
            "attached."
        )
        body = "\n\n".join(render(a) for a in earlier)
        parts.append(f"<earlier_attachments>\n{head}\n\n{body}\n</earlier_attachments>")
    if unread:
        parts.append(_UNREAD_RULE)
    return "\n\n".join(parts)
