"""
PDF manipulation tools for the Levy agent.

Three tools:
  pdf_extract_pages   — slice a page range out of a corpus document into a new artifact
  pdf_generate        — render markdown into a PDF artifact (briefs, memos, summaries)
  pdf_merge           — combine two or more existing artifacts (and/or corpus
                        document slices) into one PDF artifact

Each handler returns the same envelope shape the agent loop expects:
  {"result": {...}, "db_sources": [], "web_sources": []}
plus an additional "artifact" field (a dict) we surface to the UI as a card.

Artifacts live in the private `artifacts` Supabase Storage bucket and have a
row in `public.artifacts`. The bucket key is `<artifact_id>.pdf`.
"""

from __future__ import annotations

import io
import re
import time
from typing import Any

import httpx
import markdown as md_lib
from pypdf import PdfReader, PdfWriter
from weasyprint import HTML, CSS

from ..config import get_settings
from ..db.supabase import get_db


# ─── Storage helpers ─────────────────────────────────────────────────────────


def _upload_artifact_pdf(artifact_id: str, pdf_bytes: bytes) -> str:
    """Upload generated PDF bytes to the artifacts bucket and return its path."""
    settings = get_settings()
    base = settings.supabase_url.rstrip("/")
    key = f"{artifact_id}.pdf"
    with httpx.Client(timeout=60.0) as client:
        # Idempotent re-runs
        client.delete(
            f"{base}/storage/v1/object/artifacts/{key}",
            headers={"Authorization": f"Bearer {settings.supabase_key}"},
        )
        resp = client.post(
            f"{base}/storage/v1/object/artifacts/{key}",
            headers={
                "Authorization": f"Bearer {settings.supabase_key}",
                "Content-Type": "application/pdf",
                "x-upsert": "true",
            },
            content=pdf_bytes,
        )
        resp.raise_for_status()
    return f"artifacts/{key}"


def _download_corpus_pdf(document_id: str) -> bytes:
    """Pull a corpus document's PDF from the private legal-docs bucket."""
    db = get_db()
    res = (
        db.table("legal_documents")
        .select("pdf_storage_path")
        .eq("id", document_id)
        .limit(1)
        .execute()
    )
    if not res.data or not res.data[0].get("pdf_storage_path"):
        raise ValueError(f"document {document_id} has no stored PDF")
    path = res.data[0]["pdf_storage_path"]
    bucket, _, key = path.partition("/")
    blob = db.storage.from_(bucket).download(key)
    if not isinstance(blob, (bytes, bytearray)):
        raise RuntimeError(f"download returned {type(blob)} for {path}")
    return bytes(blob)


def _download_artifact_pdf(artifact_id: str) -> bytes:
    db = get_db()
    res = (
        db.table("artifacts")
        .select("storage_path")
        .eq("id", artifact_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise ValueError(f"artifact {artifact_id} not found")
    path = res.data[0]["storage_path"]
    bucket, _, key = path.partition("/")
    blob = db.storage.from_(bucket).download(key)
    if not isinstance(blob, (bytes, bytearray)):
        raise RuntimeError(f"download returned {type(blob)} for {path}")
    return bytes(blob)


def _insert_artifact_row(
    *,
    kind: str,
    title: str,
    storage_path: str,
    source: str,
    size_bytes: int,
    page_count: int | None,
    meta: dict,
    owner_id: str | None,
    session_id: str | None,
) -> dict:
    db = get_db()
    row = db.table("artifacts").insert(
        {
            "kind": kind,
            "title": title,
            "storage_path": storage_path,
            "source": source,
            "size_bytes": size_bytes,
            "page_count": page_count,
            "meta": meta,
            "owner_id": owner_id,
            "session_id": session_id,
        }
    ).execute()
    return row.data[0]


# ─── Tool: pdf_extract_pages ─────────────────────────────────────────────────


async def pdf_extract_pages(
    document_id: str,
    page_start: int,
    page_end: int,
    title: str | None = None,
    *,
    owner_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Slice a 1-indexed inclusive page range from a corpus PDF into a new artifact."""
    if page_start < 1 or page_end < page_start:
        return {"result": {"error": f"invalid page range {page_start}..{page_end}"}}

    src_pdf = _download_corpus_pdf(document_id)
    reader = PdfReader(io.BytesIO(src_pdf))
    total = len(reader.pages)
    end = min(page_end, total)
    start = min(page_start, total)
    if start > total:
        return {
            "result": {"error": f"page_start {page_start} exceeds document length {total}"},
        }

    writer = PdfWriter()
    for i in range(start - 1, end):
        writer.add_page(reader.pages[i])
    out = io.BytesIO()
    writer.write(out)
    pdf_bytes = out.getvalue()

    # Resolve the source act's title for a nicer artifact name
    db = get_db()
    src = (
        db.table("legal_documents")
        .select("short_name, title")
        .eq("id", document_id)
        .limit(1)
        .execute()
    )
    src_name = (src.data[0].get("short_name") if src.data else None) or (
        src.data[0].get("title") if src.data else "Source"
    )
    final_title = title or f"{src_name} — pp.{start}–{end}"

    # Insert row first to get an id we can use as the storage key
    row = _insert_artifact_row(
        kind="pdf",
        title=final_title,
        storage_path="artifacts/pending",
        source="extracted",
        size_bytes=len(pdf_bytes),
        page_count=end - start + 1,
        meta={
            "tool": "pdf_extract_pages",
            "source_document_id": document_id,
            "source_short_name": src_name,
            "page_start": start,
            "page_end": end,
        },
        owner_id=owner_id,
        session_id=session_id,
    )
    storage_path = _upload_artifact_pdf(row["id"], pdf_bytes)
    db.table("artifacts").update({"storage_path": storage_path}).eq("id", row["id"]).execute()
    row["storage_path"] = storage_path

    return {
        "result": {
            "artifact_id": row["id"],
            "title": final_title,
            "kind": "pdf",
            "page_count": end - start + 1,
            "size_bytes": len(pdf_bytes),
        },
        "artifact": row,
        "db_sources": [],
        "web_sources": [],
    }


# ─── Tool: pdf_generate ──────────────────────────────────────────────────────

# Simple, modern stylesheet for generated legal documents. Keeps inline images
# out (we don't fetch external resources) and uses safe system fonts so the
# Docker image's bundled DejaVu/Liberation set always works.
_DOCUMENT_CSS = """
@page {
  size: A4;
  margin: 22mm 18mm 22mm 18mm;
  @bottom-center {
    content: counter(page) " / " counter(pages);
    font-family: "Liberation Sans", "DejaVu Sans", sans-serif;
    font-size: 9pt;
    color: #777;
  }
}
html { font-family: "Liberation Serif", "DejaVu Serif", "Times New Roman", serif; font-size: 11pt; line-height: 1.5; color: #1a1a1a; }
h1 { font-size: 22pt; font-weight: 700; margin: 0 0 6pt 0; color: #0f3a2a; }
h2 { font-size: 15pt; font-weight: 600; margin: 16pt 0 4pt 0; border-bottom: 1px solid #d6d6d6; padding-bottom: 4pt; }
h3 { font-size: 12pt; font-weight: 600; margin: 10pt 0 3pt 0; color: #333; }
p { margin: 0 0 8pt 0; text-align: justify; }
ul, ol { margin: 0 0 8pt 18pt; padding: 0; }
li { margin-bottom: 3pt; }
hr { border: none; border-top: 1px solid #d6d6d6; margin: 14pt 0; }
blockquote { border-left: 3px solid #16a34a; padding: 2pt 12pt; margin: 8pt 0; color: #444; font-style: italic; }
code { font-family: "DejaVu Sans Mono", monospace; background: #f4f4f4; padding: 1pt 3pt; border-radius: 2pt; font-size: 10pt; }
table { border-collapse: collapse; margin: 8pt 0; width: 100%; font-size: 10pt; }
th, td { border: 1px solid #cfcfcf; padding: 4pt 6pt; text-align: left; }
th { background: #f0f0f0; }
.meta { color: #666; font-size: 9pt; margin-bottom: 14pt; }
.cite { color: #0f3a2a; font-weight: 500; }
"""


def _render_markdown_pdf(title: str, body_md: str, subtitle: str | None = None) -> bytes:
    body_html = md_lib.markdown(
        body_md,
        extensions=["extra", "tables", "sane_lists", "toc"],
    )
    subtitle_html = (
        f'<div class="meta">{subtitle}</div>' if subtitle else ""
    )
    full_html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{_html_escape(title)}</title></head>
<body>
  <h1>{_html_escape(title)}</h1>
  {subtitle_html}
  {body_html}
</body></html>"""

    pdf_bytes = HTML(string=full_html).write_pdf(stylesheets=[CSS(string=_DOCUMENT_CSS)])
    return pdf_bytes or b""


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _slug(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
    return s[:60].lower() or "untitled"


async def pdf_generate(
    title: str,
    content_markdown: str,
    subtitle: str | None = None,
    *,
    owner_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Render a markdown body into a polished PDF artifact (memos, briefs)."""
    if not title.strip():
        return {"result": {"error": "title required"}}
    if not content_markdown.strip():
        return {"result": {"error": "content_markdown required"}}

    pdf_bytes = _render_markdown_pdf(title=title, body_md=content_markdown, subtitle=subtitle)
    if not pdf_bytes:
        return {"result": {"error": "weasyprint produced no bytes"}}

    # Count pages by re-parsing what weasyprint emitted.
    try:
        page_count = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    except Exception:
        page_count = None

    row = _insert_artifact_row(
        kind="pdf",
        title=title,
        storage_path="artifacts/pending",
        source="generated",
        size_bytes=len(pdf_bytes),
        page_count=page_count,
        meta={
            "tool": "pdf_generate",
            "subtitle": subtitle,
            "slug": _slug(title),
        },
        owner_id=owner_id,
        session_id=session_id,
    )
    storage_path = _upload_artifact_pdf(row["id"], pdf_bytes)
    get_db().table("artifacts").update({"storage_path": storage_path}).eq("id", row["id"]).execute()
    row["storage_path"] = storage_path

    return {
        "result": {
            "artifact_id": row["id"],
            "title": title,
            "kind": "pdf",
            "page_count": page_count,
            "size_bytes": len(pdf_bytes),
        },
        "artifact": row,
        "db_sources": [],
        "web_sources": [],
    }


# ─── Tool: pdf_merge ─────────────────────────────────────────────────────────


async def pdf_merge(
    parts: list[dict],
    title: str,
    *,
    owner_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    """
    Concatenate multiple PDFs into one artifact.

    `parts` is a list of part dicts, each one of:
      {"artifact_id": "<uuid>"}                                   — append an existing artifact whole
      {"document_id": "<uuid>"}                                   — append a corpus PDF whole
      {"document_id": "<uuid>", "page_start": N, "page_end": M}   — append a page range from a corpus PDF
    """
    if not parts:
        return {"result": {"error": "parts must be a non-empty list"}}
    if not title.strip():
        return {"result": {"error": "title required"}}

    writer = PdfWriter()
    sources_used: list[dict] = []

    for i, part in enumerate(parts):
        try:
            if part.get("artifact_id"):
                pdf_bytes = _download_artifact_pdf(part["artifact_id"])
                src_label = f"artifact:{part['artifact_id']}"
            elif part.get("document_id"):
                pdf_bytes = _download_corpus_pdf(part["document_id"])
                src_label = f"document:{part['document_id']}"
            else:
                return {
                    "result": {"error": f"part {i} needs artifact_id or document_id"},
                }
            reader = PdfReader(io.BytesIO(pdf_bytes))
            total = len(reader.pages)
            ps = max(1, int(part.get("page_start") or 1))
            pe = min(total, int(part.get("page_end") or total))
            for p in range(ps - 1, pe):
                writer.add_page(reader.pages[p])
            sources_used.append(
                {"source": src_label, "page_start": ps, "page_end": pe, "page_count": pe - ps + 1}
            )
        except Exception as e:  # noqa: BLE001
            return {"result": {"error": f"part {i} failed: {e}"}}

    out = io.BytesIO()
    writer.write(out)
    pdf_bytes = out.getvalue()
    page_count = len(writer.pages)

    row = _insert_artifact_row(
        kind="pdf",
        title=title,
        storage_path="artifacts/pending",
        source="merged",
        size_bytes=len(pdf_bytes),
        page_count=page_count,
        meta={"tool": "pdf_merge", "parts": sources_used},
        owner_id=owner_id,
        session_id=session_id,
    )
    storage_path = _upload_artifact_pdf(row["id"], pdf_bytes)
    get_db().table("artifacts").update({"storage_path": storage_path}).eq("id", row["id"]).execute()
    row["storage_path"] = storage_path

    return {
        "result": {
            "artifact_id": row["id"],
            "title": title,
            "kind": "pdf",
            "page_count": page_count,
            "size_bytes": len(pdf_bytes),
            "parts_count": len(parts),
        },
        "artifact": row,
        "db_sources": [],
        "web_sources": [],
    }


# ─── Tool: pdf_split ─────────────────────────────────────────────────────────


async def pdf_split(
    artifact_id: str | None = None,
    document_id: str | None = None,
    ranges: list[dict] | None = None,
    title_prefix: str | None = None,
    *,
    owner_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    """
    Split a PDF (artifact or corpus document) into multiple smaller artifacts.

    `ranges` is a list of `{"page_start": N, "page_end": M, "title": "..."}`
    descriptors. Each yields one artifact. If `title` is omitted on a range,
    we synthesise `<title_prefix or 'Split'> — pp.N–M`.
    """
    if (artifact_id is None) == (document_id is None):
        return {"result": {"error": "specify exactly one of artifact_id or document_id"}}
    if not ranges:
        return {"result": {"error": "ranges must be a non-empty list"}}

    src_pdf = (
        _download_artifact_pdf(artifact_id) if artifact_id
        else _download_corpus_pdf(document_id or "")
    )
    reader = PdfReader(io.BytesIO(src_pdf))
    total_pages = len(reader.pages)

    # Resolve a sensible default title prefix.
    db = get_db()
    if not title_prefix:
        if artifact_id:
            r = db.table("artifacts").select("title").eq("id", artifact_id).limit(1).execute()
            title_prefix = (r.data[0].get("title") if r.data else None) or "Split"
        else:
            r = db.table("legal_documents").select("short_name, title").eq("id", document_id).limit(1).execute()
            title_prefix = (
                (r.data[0].get("short_name") if r.data else None)
                or (r.data[0].get("title") if r.data else None)
                or "Split"
            )

    produced: list[dict] = []
    for i, rng in enumerate(ranges):
        try:
            ps = max(1, int(rng.get("page_start") or 1))
            pe = min(total_pages, int(rng.get("page_end") or total_pages))
            if pe < ps:
                produced.append({"index": i, "error": f"invalid range {ps}..{pe}"})
                continue
            writer = PdfWriter()
            for p in range(ps - 1, pe):
                writer.add_page(reader.pages[p])
            out = io.BytesIO()
            writer.write(out)
            pdf_bytes = out.getvalue()
            piece_title = (rng.get("title") or f"{title_prefix} — pp.{ps}–{pe}").strip()
            row = _insert_artifact_row(
                kind="pdf",
                title=piece_title,
                storage_path="artifacts/pending",
                source="extracted",
                size_bytes=len(pdf_bytes),
                page_count=pe - ps + 1,
                meta={
                    "tool": "pdf_split",
                    "source_artifact_id": artifact_id,
                    "source_document_id": document_id,
                    "page_start": ps,
                    "page_end": pe,
                },
                owner_id=owner_id,
                session_id=session_id,
            )
            storage_path = _upload_artifact_pdf(row["id"], pdf_bytes)
            db.table("artifacts").update({"storage_path": storage_path}).eq("id", row["id"]).execute()
            row["storage_path"] = storage_path
            produced.append({
                "artifact_id": row["id"],
                "title": piece_title,
                "page_start": ps,
                "page_end": pe,
                "page_count": pe - ps + 1,
                "_artifact": row,
            })
        except Exception as e:  # noqa: BLE001
            produced.append({"index": i, "error": str(e)})

    # Surface every artifact as its own card via the agent loop's "artifact"
    # event. The first one goes in `artifact`; the rest piggy-back via
    # `extra_artifacts` so the loop emits them too.
    succeeded = [p for p in produced if p.get("artifact_id")]
    primary = succeeded[0]["_artifact"] if succeeded else None
    extras = [p["_artifact"] for p in succeeded[1:]]
    for p in produced:
        p.pop("_artifact", None)

    return {
        "result": {
            "produced": produced,
            "count": len(succeeded),
        },
        "artifact": primary,
        "extra_artifacts": extras,
        "db_sources": [],
        "web_sources": [],
    }


# ─── Tool: export_thread_brief ───────────────────────────────────────────────
# The premium-edge feature: turn an entire chat thread into a polished PDF
# brief with an appendix that includes the relevant page ranges from every
# corpus document the assistant cited.


def _strip_user_thinking(text: str) -> str:
    """Light cleanup for the assistant's prose before embedding it in the brief.
    Drops residual streaming artifacts (cursor pipes, isolated whitespace)."""
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    return "\n".join(ln for ln in lines if ln is not None)


async def export_thread_brief(
    session_id: str,
    title: str | None = None,
    include_appendix: bool = True,
    *,
    owner_id: str | None = None,
) -> dict:
    """
    Compose a single PDF brief for the entire conversation:
      1. Cover page (title + matter line + date).
      2. Q&A transcript (each user question + the assistant's answer).
      3. Appendix (when include_appendix=true): for every distinct corpus
         document cited, pull the cited page ranges (deduped + merged into
         contiguous spans) and append them to the PDF.
    """
    db = get_db()
    sess = (
        db.table("chat_sessions").select("id, title, user_id, created_at")
        .eq("id", session_id).limit(1).execute()
    )
    if not sess.data:
        return {"result": {"error": f"session {session_id} not found"}}
    sess_row = sess.data[0]

    msgs = (
        db.table("chat_messages")
        .select("role, content, citations, created_at")
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .execute()
    ).data or []

    if not msgs:
        return {"result": {"error": "thread is empty"}}

    # ── Build the prose body in Markdown for weasyprint ─────────────────────
    final_title = (title or sess_row.get("title") or "Levy Brief").strip() or "Levy Brief"
    md_lines: list[str] = []
    md_lines.append(f"_Generated from a Levy consultation on {sess_row.get('created_at','')[:10]}._")
    md_lines.append("")

    # Aggregate citations by document_id and merge page ranges. Legacy
    # citation snapshots (pre-Phase-2) only carry `act_name` — for those we
    # fall back to a title lookup so the appendix still works on old threads.
    cite_spans: dict[str, dict] = {}  # doc_id -> {"act_name": ..., "spans": list[(ps,pe)]}
    title_to_doc_id: dict[str, str | None] = {}

    def _resolve_doc_id(act_name: str | None) -> str | None:
        if not act_name:
            return None
        if act_name in title_to_doc_id:
            return title_to_doc_id[act_name]
        try:
            res = (
                db.table("legal_documents").select("id, title")
                .eq("title", act_name).limit(1).execute()
            )
            if not res.data:
                # Loose match — prior versions stored uppercased titles.
                token = max(act_name.split(), key=len) if act_name.strip() else ""
                if token:
                    res = (
                        db.table("legal_documents").select("id, title")
                        .ilike("title", f"%{token}%").limit(1).execute()
                    )
            doc_id = res.data[0]["id"] if res.data else None
        except Exception:
            doc_id = None
        title_to_doc_id[act_name] = doc_id
        return doc_id

    for m in msgs:
        role = m.get("role")
        content = m.get("content") or ""
        if role == "user":
            md_lines.append("## " + (content.splitlines()[0][:120] if content else "(empty)"))
            md_lines.append("")
            md_lines.append(content)
        elif role == "assistant":
            md_lines.append("")
            md_lines.append("**Levy AI:**")
            md_lines.append("")
            md_lines.append(_strip_user_thinking(content))
            for c in m.get("citations") or []:
                if not isinstance(c, dict):
                    continue
                doc_id = c.get("document_id") or _resolve_doc_id(c.get("act_name"))
                if not doc_id:
                    continue
                ps = c.get("page_start")
                pe = c.get("page_end") or ps
                if not ps:
                    continue
                slot = cite_spans.setdefault(
                    doc_id,
                    {"act_name": c.get("act_name"), "spans": []},
                )
                slot["spans"].append((int(ps), int(pe)))
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    body_md = "\n".join(md_lines).rstrip()

    # ── Generate the prose PDF ──────────────────────────────────────────────
    prose_bytes = _render_markdown_pdf(
        title=final_title,
        body_md=body_md,
        subtitle="Compiled by Levy from this consultation.",
    )
    if not prose_bytes:
        return {"result": {"error": "weasyprint produced no bytes"}}

    appendix_pages_added = 0
    appendix_index: list[dict] = []  # for the artifact meta record

    # ── Optionally append cited corpus page-ranges ──────────────────────────
    final_writer = PdfWriter()
    for page in PdfReader(io.BytesIO(prose_bytes)).pages:
        final_writer.add_page(page)

    if include_appendix and cite_spans:
        # Render an appendix cover page.
        cover_md_lines = ["## Appendix", "", "Cited statutory excerpts, in the order cited:", ""]
        # Sort docs by act name for stable order.
        sorted_docs = sorted(cite_spans.items(), key=lambda kv: (kv[1].get("act_name") or "").lower())
        for doc_id, info in sorted_docs:
            spans = info.get("spans") or []
            if not spans:
                continue
            # Merge overlapping/adjacent spans.
            spans.sort()
            merged: list[list[int]] = []
            for ps, pe in spans:
                if merged and ps <= merged[-1][1] + 1:
                    merged[-1][1] = max(merged[-1][1], pe)
                else:
                    merged.append([ps, pe])
            label = info.get("act_name") or "Source"
            ranges_str = ", ".join(
                f"pp.{ps}" if ps == pe else f"pp.{ps}–{pe}" for ps, pe in merged
            )
            cover_md_lines.append(f"- **{label}** — {ranges_str}")
        cover_bytes = _render_markdown_pdf(
            title=final_title,
            body_md="\n".join(cover_md_lines),
            subtitle="Appendix index",
        )
        for page in PdfReader(io.BytesIO(cover_bytes)).pages:
            final_writer.add_page(page)

        for doc_id, info in sorted_docs:
            spans = info.get("spans") or []
            if not spans:
                continue
            try:
                doc_pdf = _download_corpus_pdf(doc_id)
            except Exception:
                continue
            doc_reader = PdfReader(io.BytesIO(doc_pdf))
            doc_pages = len(doc_reader.pages)
            spans.sort()
            merged: list[list[int]] = []
            for ps, pe in spans:
                if merged and ps <= merged[-1][1] + 1:
                    merged[-1][1] = max(merged[-1][1], pe)
                else:
                    merged.append([ps, pe])
            for ps, pe in merged:
                ps = max(1, ps)
                pe = min(doc_pages, pe)
                if pe < ps:
                    continue
                for p in range(ps - 1, pe):
                    final_writer.add_page(doc_reader.pages[p])
                appendix_pages_added += pe - ps + 1
                appendix_index.append({
                    "document_id": doc_id,
                    "act_name": info.get("act_name"),
                    "page_start": ps,
                    "page_end": pe,
                })

    out = io.BytesIO()
    final_writer.write(out)
    pdf_bytes = out.getvalue()
    page_count = len(final_writer.pages)

    row = _insert_artifact_row(
        kind="pdf",
        title=final_title,
        storage_path="artifacts/pending",
        source="generated",
        size_bytes=len(pdf_bytes),
        page_count=page_count,
        meta={
            "tool": "export_thread_brief",
            "session_id": session_id,
            "with_appendix": include_appendix,
            "appendix_pages": appendix_pages_added,
            "appendix_index": appendix_index,
            "messages_included": len(msgs),
        },
        owner_id=owner_id or sess_row.get("user_id"),
        session_id=session_id,
    )
    storage_path = _upload_artifact_pdf(row["id"], pdf_bytes)
    db.table("artifacts").update({"storage_path": storage_path}).eq("id", row["id"]).execute()
    row["storage_path"] = storage_path

    return {
        "result": {
            "artifact_id": row["id"],
            "title": final_title,
            "kind": "pdf",
            "page_count": page_count,
            "size_bytes": len(pdf_bytes),
            "appendix_pages": appendix_pages_added,
            "documents_in_appendix": len(appendix_index),
        },
        "artifact": row,
        "db_sources": [],
        "web_sources": [],
    }
