"""What the model is told about the documents a user attached to a chat.

Twice a user attached a document whose text never reached the model, and the
answer admitted it only later ("flagged but the text content has not come
through"). Small attachments were listed as "inline" whether or not any text
had loaded: a scan has no text layer, and a document past the per-turn budget
was dropped silently. Each attachment now carries an honest status, and an
unread one comes with the way to read it.
"""
from __future__ import annotations

INLINE_MAX_CHARS = 30_000   # per attachment
INLINE_TOTAL_CAP = 60_000   # across all inline attachments in one turn


def looks_scanned(text: str | None, page_count: int | None) -> bool:
    """Too little text for its pages: a scan, a photo, or a PDF of images.

    A typed page carries well over a thousand characters; under 80 a page is a
    header or a stamp at most.
    """
    return len((text or "").strip()) < 80 * max(1, page_count or 1)


def attachment_block(rows: list[dict], texts: dict[str, str]) -> str:
    """The system-prompt section listing the attachments.

    `rows`: legal_documents rows (id, title, short_name, pdf_page_count,
    total_chunks). `texts`: stored inline text by document id, where it exists.
    """
    lines: list[str] = []
    inline_sections: list[str] = []
    unread = 0
    used = 0
    for r in rows:
        name = (r.get("short_name") or r.get("title") or "untitled").strip()
        pages = r.get("pdf_page_count")
        size = f"{pages} pages, " if pages else ""
        if (r.get("total_chunks") or 0) > 0:
            lines.append(f'  - "{name}" ({size}searchable: use search_corpus)')
            continue
        text = (texts.get(r["id"]) or "").strip()
        if looks_scanned(text, pages):
            lines.append(f'  - "{name}" ({size}NOT READ: no text layer, probably a scan or photo; '
                         f'document_id {r["id"]})')
            unread += 1
            continue
        if used >= INLINE_TOTAL_CAP:
            lines.append(f'  - "{name}" ({size}NOT READ: past this turn\'s size limit; document_id {r["id"]})')
            unread += 1
            continue
        budget = min(INLINE_MAX_CHARS, INLINE_TOTAL_CAP - used)
        snippet = text[:budget]
        cut = len(text) > budget
        used += len(snippet)
        inline_sections.append(f"### Attachment: {name}\n{snippet}"
                               + (f"\n\n[truncated here: read the rest with read_pdf_pages, document_id {r['id']}]"
                                  if cut else ""))
        lines.append(f'  - "{name}" ({size}full text below{", truncated" if cut else ""})')

    block = (
        "\n\n## User attachments for this conversation\n"
        "The user has attached these documents to this chat:\n"
        + "\n".join(lines)
        + "\n\nREAD THE ATTACHMENTS FIRST. For a searchable attachment, your first tool call "
        "must be `search_corpus` with a query drawn from the user's question; the results "
        "will include it. Where the full text is below, read it directly and do NOT search "
        "for it. Do not call gov_search / web_search / news_search until you have read the "
        "attachments. Cite attachments by name when you quote them."
    )
    if unread:
        block += (
            "\n\nSOME ATTACHMENTS HAVE NOT BEEN READ (marked NOT READ above). Before you say "
            "anything about their contents, read them with `read_pdf_pages` and the "
            "document_id shown: pages with no text come back as images you can read, at most "
            "6 pages per call. If a file still cannot be read, say so plainly at the START of "
            "your answer and ask the user to paste the part that matters or send a clearer "
            "copy. Never describe, summarise or rely on a document you have not read."
        )
    if inline_sections:
        block += (
            "\n\n## Inline attachment contents\n"
            "These are the texts of the attachments marked 'full text below'.\n\n"
            + "\n\n---\n\n".join(inline_sections)
        )
    return block
