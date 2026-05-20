"""
Form / application / guidance-document ingester.

Used to add Zambian government and institutional PDFs to the global library
that are NOT statutes — e.g. PACRA Form 5 (company registration), the ZRA
TPIN application, the Immigration work-permit form, BoZ licensing
checklists, ZICTA licensing forms, NAPSA registration, the Lands Title
Deed application, fee schedules, civil-procedure rules, etc.

The Acts ingester (`ingester.ingest_pdf`) parses the document into Part /
Section / Subsection structure. That works because Acts have a well-known
typography. Forms don't — they're a few pages of fields, instructions,
and fee tables. So this module takes a different approach:

  1. Hash the PDF for deduplication.
  2. Extract the text page by page.
  3. Build chunks at the page level (small forms collapse to one chunk).
  4. Prepend a synthesised "Title — Description" header to each chunk so
     vector search keys off the form's purpose, not just whatever the
     PDF text happens to say.
  5. Embed and store with `document_type` = 'form' / 'application' /
     'guide' / 'fee_schedule'.

The caller is responsible for uploading the PDF to Supabase storage and
patching `pdf_storage_path` / `is_global` afterwards — same convention
the Acts scraper uses.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader

from .embedder import get_embeddings
from .parser import get_pdf_hash
from ..db.supabase import (
    insert_document,
    insert_chunks,
    get_document_by_hash,
)


# Forms are short. We prefer ~1 chunk per page so a search hit lands on the
# right page out of the box and the PDF viewer can deep-link to it. Pages
# shorter than this floor get merged with the next page to avoid spammy
# 50-character chunks.
PAGE_MIN_CHARS = 200
# Don't let an unusually-long brochure page balloon a single chunk past
# what the embedding model takes happily.
PAGE_MAX_CHARS = 4500


def _read_pages(pdf_path: str) -> list[str]:
    reader = PdfReader(pdf_path)
    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            text = ""
        # Collapse pdf wrapping whitespace; the model doesn't need it and
        # it inflates the chunk size.
        text = " ".join(text.split())
        pages.append(text)
    return pages


def _bucket_pages_into_chunks(pages: Iterable[str]) -> list[dict]:
    """Yield {"text", "page_start", "page_end"} dicts.

    Short pages get glued onto the next page; long pages stand alone (and
    are truncated to PAGE_MAX_CHARS — fine for embeddings, the original
    page text is still retrievable from the PDF itself).
    """
    chunks: list[dict] = []
    buffer = ""
    buffer_start: int | None = None
    for i, text in enumerate(pages, start=1):
        if not text.strip():
            continue
        if buffer_start is None:
            buffer_start = i

        # If adding this page would overflow, flush the buffer first.
        if buffer and len(buffer) + len(text) + 1 > PAGE_MAX_CHARS:
            chunks.append({
                "text": buffer.strip(),
                "page_start": buffer_start,
                "page_end": i - 1,
            })
            buffer = text[:PAGE_MAX_CHARS]
            buffer_start = i
            continue

        buffer = (buffer + "\n" + text) if buffer else text
        if len(buffer) >= PAGE_MIN_CHARS:
            chunks.append({
                "text": buffer.strip()[:PAGE_MAX_CHARS],
                "page_start": buffer_start,
                "page_end": i,
            })
            buffer = ""
            buffer_start = None

    if buffer.strip() and buffer_start is not None:
        chunks.append({
            "text": buffer.strip()[:PAGE_MAX_CHARS],
            "page_start": buffer_start,
            "page_end": len(list(pages)) if isinstance(pages, list) else buffer_start,
        })
    return chunks


def ingest_form_pdf(
    pdf_path: str,
    *,
    title: str,
    short_name: str | None = None,
    description: str = "",
    document_type: str = "form",
    category: str | None = None,
    issuing_authority: str | None = None,
    source_url: str | None = None,
    force: bool = False,
) -> dict:
    """Ingest a non-statute PDF (form, application, guide, fee schedule).

    Required: an authoritative `title` (e.g. "PACRA Form 5 — Application
    for Registration of a Private Company Limited by Shares") and at
    least a short `description`. These get used for the synthesised
    chunk header AND end up in document metadata so the agent can quote
    them when recommending the form.

    `document_type` is one of: 'form', 'application', 'guide', 'fee_schedule',
    'checklist', 'circular'. Anything outside the 'act' lane.
    """
    pdf_path = str(Path(pdf_path).resolve())
    print(f"\n  Ingesting form: {Path(pdf_path).name}")
    print(f"    Title: {title}")

    pdf_hash = get_pdf_hash(pdf_path)
    existing = get_document_by_hash(pdf_hash)
    if existing and not force:
        print(f"    Already ingested as: {existing['title']}")
        return {"status": "skipped", "document": existing}

    pages = _read_pages(pdf_path)
    if not pages or not any(p.strip() for p in pages):
        print("    No extractable text — possibly scanned image; ingesting anyway as a one-chunk header so it's still discoverable.")
        # Even if the PDF is image-only, we want the form to appear in
        # search results — embed the title + description so the agent
        # can recommend it. The user opens the PDF for the visual form.
        page_chunks = []
    else:
        page_chunks = _bucket_pages_into_chunks(pages)

    # Always seed at least one "header" chunk so the agent can find this
    # form by description even when its PDF text is unreadable. Put it
    # FIRST so it gets the highest weighting on vector match.
    header_lines = [f"{title}"]
    if short_name and short_name != title:
        header_lines.append(f"({short_name})")
    if issuing_authority:
        header_lines.append(f"Issued by: {issuing_authority}")
    if category:
        header_lines.append(f"Category: {category}")
    if description:
        header_lines.append("")
        header_lines.append(description)
    header_text = "\n".join(header_lines)

    all_chunks = [{
        "text": header_text,
        "page_start": 1,
        "page_end": 1,
    }] + page_chunks

    # Insert document record. document_type tells callers (and the
    # frontend filter) this is not a statute.
    doc_record = insert_document({
        "title": title,
        "short_name": short_name or title,
        "document_type": document_type,
        "pdf_hash": pdf_hash,
        "total_sections": 0,
        # source_url is rendered as "Open original" in the viewer.
        # We'll let the caller patch canonical_url + storage_path later.
    })
    document_id = doc_record["id"]
    print(f"    Document ID: {document_id}")

    # Embed in batches; the embedder service handles batching internally.
    texts = [c["text"] for c in all_chunks]
    embeddings = get_embeddings(texts)

    rows = []
    citation_label = short_name or title
    for i, (chunk, embedding) in enumerate(zip(all_chunks, embeddings)):
        rows.append({
            "document_id": document_id,
            "content": chunk["text"],
            "embedding": embedding,
            "metadata": {
                # `act_name` is the field the search-citation card renders
                # in the UI. We reuse it for forms / applications too so the
                # citation reads "PACRA Form 5" rather than "Unknown Act".
                "act_name": citation_label,
                "document_type": document_type,
                "category": category,
                "issuing_authority": issuing_authority,
                "is_header": i == 0,
            },
            "chunk_index": i,
            "page_start": chunk["page_start"],
            "page_end": chunk["page_end"],
        })

    stored = insert_chunks(rows)
    from ..db.supabase import get_db
    get_db().table("legal_documents").update({
        "total_chunks": len(stored),
    }).eq("id", document_id).execute()

    print(f"    {len(stored)} chunks stored.")
    return {
        "status": "success",
        "document": doc_record,
        "chunks_created": len(stored),
        "pages_processed": len([p for p in pages if p.strip()]),
    }
