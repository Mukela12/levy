#!/usr/bin/env python3
"""Safely ingest the curated Parliament refresh staging set.

This command intentionally refuses to run with the application's configured
OpenAI key.  Set HARVEST_OPENAI_API_KEY to a temporary, non-production key (in
the environment or ignored backend/.env.harvest) and pass --execute.  Parsing
and embedding finish before any database row changes.

Examples:
  python scripts/ingest_staged_parliament_acts.py --staging-dir /path/to/stage
  HARVEST_OPENAI_API_KEY=... python scripts/ingest_staged_parliament_acts.py \
      --staging-dir /path/to/stage --execute
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
DEFAULT_PLAN = Path(__file__).with_name("parliament_refresh_2026_09_16_plan.json")


def _read_env_file(path: Path) -> dict[str, str]:
    """Read enough dotenv syntax to compare secrets without importing the app."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")[:120]


def _load_plan(path: Path, staging_dir: Path, only: set[str]) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("items", [])
    selected: list[dict[str, Any]] = []
    for item in items:
        if only and item["key"] not in only:
            continue
        item = dict(item)
        item["original_path"] = staging_dir / item["original_file"]
        parser_file = item.get("parser_file") or item["original_file"]
        item["parser_path"] = staging_dir / parser_file
        selected.append(item)
    missing = only - {i["key"] for i in selected}
    if missing:
        raise SystemExit(f"Unknown --only key(s): {', '.join(sorted(missing))}")
    return selected


def _validate_item(item: dict[str, Any]) -> None:
    for field in ("original_path", "parser_path"):
        path = item[field]
        if not path.is_file():
            raise RuntimeError(f"{item['key']}: missing {field}: {path}")
    actual = _sha256(item["original_path"])
    if actual != item["sha256"]:
        raise RuntimeError(
            f"{item['key']}: official PDF hash mismatch; expected {item['sha256']}, got {actual}"
        )
    if item["action"] == "replace" and not item.get("document_id"):
        raise RuntimeError(f"{item['key']}: replace action requires document_id")


def _configure_harvest_key() -> None:
    harvest_file = _read_env_file(BACKEND / ".env.harvest")
    temporary = (
        os.environ.get("HARVEST_OPENAI_API_KEY", "").strip()
        or harvest_file.get("HARVEST_OPENAI_API_KEY", "").strip()
    )
    if not temporary:
        raise SystemExit(
            "Refusing to execute: set HARVEST_OPENAI_API_KEY to a temporary, "
            "non-production OpenAI key in the environment or backend/.env.harvest."
        )
    dotenv_key = _read_env_file(BACKEND / ".env").get("OPENAI_API_KEY", "").strip()
    environment_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if temporary in {key for key in (dotenv_key, environment_key) if key}:
        raise SystemExit(
            "Refusing to execute: HARVEST_OPENAI_API_KEY matches backend/.env. "
            "Use a separate temporary key."
        )

    # app.config loads backend/.env at import time with override=True.  Import
    # it first, then replace only the embedding credentials and clear the
    # cached Settings object before any database/embedder module is imported.
    sys.path.insert(0, str(BACKEND))
    from app import config

    os.environ["OPENAI_API_KEY"] = temporary
    os.environ["OPENAI_API_KEY_FALLBACK"] = ""
    os.environ["OPENAI_FALLBACK_BASE_URL"] = ""
    os.environ["EMBEDDING_PROVIDER"] = "openai"
    config.get_settings.cache_clear()
    settings = config.get_settings()
    if settings.openai_api_key != temporary or settings.openai_api_key_fallback:
        raise SystemExit("Refusing to execute: temporary-key isolation check failed.")


def _storage_upload(db: Any, key: str, body: bytes) -> str:
    db.storage.from_("legal-docs").upload(
        key,
        body,
        file_options={"content-type": "application/pdf", "upsert": "false"},
    )
    return f"legal-docs/{key}"


def _storage_remove(db: Any, storage_path: str | None) -> None:
    if not storage_path:
        return
    bucket, _, key = storage_path.partition("/")
    if bucket and key:
        db.storage.from_(bucket).remove([key])


def _delete_chunk_ids(db: Any, ids: list[str]) -> None:
    for start in range(0, len(ids), 100):
        db.table("legal_chunks").delete().in_("id", ids[start : start + 100]).execute()


def _insert_chunk_rows(db: Any, rows: list[dict[str, Any]]) -> list[str]:
    # Each row carries a 768-float embedding into an indexed pgvector column,
    # and Supabase cancels inserts much above five such rows (57014, statement
    # timeout). Row ids are fixed before the insert, so a retry asks which ids
    # already landed and sends only the rest.
    inserted: set[str] = set()
    for start in range(0, len(rows), 5):
        batch = rows[start : start + 5]
        for attempt in range(4):
            try:
                result = db.table("legal_chunks").insert(batch).execute()
                inserted.update(row["id"] for row in (result.data or []))
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))
                held = (
                    db.table("legal_chunks").select("id")
                    .in_("id", [row["id"] for row in batch]).execute().data or []
                )
                inserted.update(row["id"] for row in held)
                batch = [row for row in batch if row["id"] not in inserted]
                if not batch:
                    break
    if len(inserted) != len(rows):
        raise RuntimeError(f"stored {len(inserted)} of {len(rows)} chunks")
    return [row["id"] for row in rows]


def _page_count(path: Path) -> int:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        return len(pdf.pages)


def _prepare(item: dict[str, Any], document_id: str) -> tuple[list[Any], int]:
    from app.services.chunker import chunk_sections
    from app.services.parser import parse_legal_pdf

    parsed = parse_legal_pdf(str(item["parser_path"]))
    metadata = {
        "title": item["title"],
        "short_name": item["short_name"],
        "act_number": item.get("act_number", ""),
        "year": item.get("year"),
    }
    chunks = chunk_sections(parsed["sections"], metadata, document_id)
    if not chunks:
        # A one-page repeal or appropriation Act prints its section numbers in
        # the margin, and OCR drops them: "1. This Act may be cited" arrives as
        # "This Act may be cited ... Short title". The statute parser then sees
        # no sections. Losing the whole Act over its numbering is worse than
        # indexing the page as it reads, so fall back to the raw text.
        chunks = _plain_chunks(parsed, metadata, document_id)
        if not chunks:
            raise RuntimeError(f"{item['key']}: neither sections nor text")
        print("  no numbered sections survived OCR; indexed as plain text", flush=True)
    sections = sum(section.level == "section" for section in parsed["sections"])
    return chunks, sections


def _plain_chunks(parsed: dict[str, Any], metadata: dict[str, Any], document_id: str) -> list[Any]:
    """Whole-page text as chunks, for a document the section parser cannot read."""
    from app.models.schemas import LegalChunk

    name = metadata.get("short_name") or metadata.get("title") or ""
    rows: list[Any] = []
    for page in parsed.get("raw_pages", []):
        text = (page.get("text") or "").strip()
        if len(text) < 40:
            continue
        rows.append(LegalChunk(
            document_id=document_id,
            content=f"{name} - page {page['page_number']}\n\n{text}",
            summary=None,
            metadata={"act_name": name, "act_title": metadata.get("title", ""),
                      "act_number": metadata.get("act_number", ""), "year": metadata.get("year"),
                      "level": "page", "section_number": None, "section_title": None,
                      "part_number": None, "page_start": page["page_number"],
                      "page_end": page["page_number"], "cross_references": []},
            chunk_index=len(rows),
            page_start=page["page_number"],
            page_end=page["page_number"],
        ))
    return rows


def _rows_for_chunks(
    item: dict[str, Any], chunks: list[Any], embeddings: list[list[float]], run_tag: str
) -> list[dict[str, Any]]:
    if len(chunks) != len(embeddings):
        raise RuntimeError("embedding count does not match chunk count")
    rows: list[dict[str, Any]] = []
    for chunk, embedding in zip(chunks, embeddings):
        metadata = dict(chunk.metadata)
        metadata.update(
            {
                "source_url": item["source_url"],
                "ingestion_run": run_tag,
                "text_provenance": (
                    "Apple Vision OCR with visual QA"
                    if item.get("parser_file")
                    else "official PDF text"
                ),
            }
        )
        rows.append(
            {
                "id": str(uuid.uuid4()),
                "document_id": chunk.document_id,
                "content": chunk.content,
                "summary": chunk.summary,
                "embedding": embedding,
                "metadata": metadata,
                "chunk_index": chunk.chunk_index,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
            }
        )
    return rows


def _document_fields(
    item: dict[str, Any], document_id: str, storage_path: str, sections: int, chunks: int
) -> dict[str, Any]:
    return {
        "id": document_id,
        "title": item["title"],
        "short_name": item["short_name"],
        "act_number": item.get("act_number", ""),
        "year": item.get("year"),
        # Rules and statutory instruments keep their own type so the Acts
        # directory and the law map only see Acts.
        "document_type": item.get("document_type", "act"),
        "source_url": item["source_url"],
        "canonical_url": item["source_url"],
        "pdf_hash": item["sha256"],
        "pdf_storage_path": storage_path,
        "pdf_page_count": _page_count(item["original_path"]),
        "pdf_size_bytes": item["original_path"].stat().st_size,
        "total_sections": sections,
        "total_chunks": chunks,
        "is_global": True,
        "owner_id": None,
    }


def _ingest_one(item: dict[str, Any]) -> dict[str, Any]:
    from app.db.supabase import get_db
    from app.services.embedder import get_embeddings

    db = get_db()
    duplicate = (
        db.table("legal_documents")
        .select("id,title,total_chunks")
        .eq("pdf_hash", item["sha256"])
        .execute()
        .data
        or []
    )
    if duplicate:
        held = duplicate[0]
        exact = (
            db.table("legal_chunks")
            .select("id", count="exact")
            .eq("document_id", held["id"])
            .limit(1)
            .execute()
        ).count
        if held.get("total_chunks") and exact == held["total_chunks"]:
            if item["action"] == "ingest" or held["id"] == item.get("document_id"):
                return {
                    "key": item["key"],
                    "status": "already-held",
                    "document_id": held["id"],
                    "chunks": exact,
                }
        raise RuntimeError(
            f"{item['key']}: matching hash is present but its chunk state is inconsistent; "
            "inspect before retrying"
        )

    document_id = item.get("document_id") or str(uuid.uuid4())
    if item["action"] == "replace":
        existing = (
            db.table("legal_documents").select("id").eq("id", document_id).limit(1).execute().data or []
        )
        if not existing:
            raise RuntimeError(f"{item['key']}: replacement document {document_id} no longer exists")

    chunks, sections = _prepare(item, document_id)
    print(f"  Prepared {len(chunks)} chunks; embedding before database mutation...")
    embeddings = get_embeddings([chunk.content for chunk in chunks])
    run_tag = f"parliament-refresh-2026-09-16:{item['key']}"
    rows = _rows_for_chunks(item, chunks, embeddings, run_tag)
    planned_ids = [row["id"] for row in rows]

    key = f"{item.get('storage_prefix', 'parliament-acts')}/{document_id}/{_slug(item['original_file'])}"
    storage_path: str | None = None
    replacement_swap_started = False
    try:
        storage_path = _storage_upload(db, key, item["original_path"].read_bytes())
        doc_fields = _document_fields(item, document_id, storage_path, sections, len(rows))

        if item["action"] == "ingest":
            db.table("legal_documents").insert(doc_fields).execute()
            _insert_chunk_rows(db, rows)
        else:
            old_rows = (
                db.table("legal_chunks").select("id").eq("document_id", document_id).execute().data or []
            )
            old_ids = [row["id"] for row in old_rows]
            _insert_chunk_rows(db, rows)
            # The new searchable copy exists before the old one is removed.
            update_fields = dict(doc_fields)
            update_fields.pop("id", None)
            replacement_swap_started = True
            db.table("legal_documents").update(update_fields).eq("id", document_id).execute()
            _delete_chunk_ids(db, old_ids)

        exact = (
            db.table("legal_chunks")
            .select("id", count="exact")
            .eq("document_id", document_id)
            .limit(1)
            .execute()
        )
        if exact.count != len(rows):
            raise RuntimeError(
                f"post-write verification found {exact.count} chunks; expected {len(rows)}"
            )
        return {
            "key": item["key"],
            "status": "ingested" if item["action"] == "ingest" else "replaced",
            "document_id": document_id,
            "chunks": len(rows),
            "sections": sections,
            "pages": doc_fields["pdf_page_count"],
        }
    except Exception:
        if item["action"] == "ingest":
            # The UUID is generated for this run, so this is safe even if the
            # insert's response was lost after the server committed it.
            db.table("legal_documents").delete().eq("id", document_id).execute()
            _storage_remove(db, storage_path)
        elif item["action"] == "replace" and replacement_swap_started:
            # Never delete replacement rows after old rows may have been
            # removed: duplicates are recoverable; missing law text is not.
            print(
                "  Replacement stopped after mutation. New rows/storage were retained "
                "to avoid data loss; inspect before retrying."
            )
        elif item["action"] == "replace":
            # Old chunks are untouched until replacement_swap_started.  Row
            # IDs were predetermined, so this also clears a partially
            # successful multi-batch insert.
            _delete_chunk_ids(db, planned_ids)
            _storage_remove(db, storage_path)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--staging-dir", type=Path, required=True)
    parser.add_argument("--only", action="append", default=[], metavar="KEY")
    parser.add_argument("--execute", action="store_true", help="embed and write to Supabase")
    args = parser.parse_args()

    items = _load_plan(args.plan.resolve(), args.staging_dir.resolve(), set(args.only))
    if not items:
        raise SystemExit("No plan items selected")
    for item in items:
        _validate_item(item)

    print(f"Validated {len(items)} curated Parliament item(s).")
    for item in items:
        suffix = " [Vision OCR]" if item.get("parser_file") else ""
        print(f"  {item['key']}: {item['action']} — {item['title']}{suffix}")

    if not args.execute:
        print("Dry run only. Pass --execute with HARVEST_OPENAI_API_KEY to ingest.")
        return 0

    _configure_harvest_key()
    results: list[dict[str, Any]] = []
    for index, item in enumerate(items, 1):
        print(f"\n[{index}/{len(items)}] {item['title']}")
        results.append(_ingest_one(item))

    print("\nCompleted staged Parliament ingestion:")
    for result in results:
        print("  " + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
