#!/usr/bin/env python3
"""
Ingest the curated global library into the new Levy Supabase project.

For every PDF in INPUT_DIR:
  1. Skip if the PDF hash already exists (idempotent re-runs are safe).
  2. Upload the PDF bytes to the private `legal-docs` Supabase Storage bucket
     so citation clicks can stream the file back.
  3. Run the standard `ingest_pdf` pipeline (parse → chunk → embed via OpenAI
     text-embedding-3-small @ 768d → insert into legal_chunks).
  4. Patch the freshly-created legal_documents row with
     pdf_storage_path / pdf_page_count / pdf_size_bytes / is_global=True so
     the UI knows it's part of the global library and can render the PDF.

Run with:
  /Users/mukelakatungu/levy/.claude/worktrees/lucid-bartik-c2ad7f/.venv/bin/python \
      scripts/ingest_global_library.py
"""

from __future__ import annotations

import hashlib
import re
import sys
import uuid
from pathlib import Path

# Make the backend importable
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from dotenv import load_dotenv

load_dotenv(REPO / "backend" / ".env")

from app.db.supabase import get_db  # noqa: E402
from app.services.ingester import ingest_pdf  # noqa: E402


INPUT_DIR = Path(
    "/Users/mukelakatungu/Library/Mobile Documents/com~apple~CloudDocs/Desktop/Levy Training documents"
)
BUCKET = "legal-docs"


def slugify(name: str) -> str:
    """Filename-safe slug for a storage key."""
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return base or uuid.uuid4().hex


def pdf_already_ingested(pdf_hash: str) -> dict | None:
    res = (
        get_db()
        .table("legal_documents")
        .select("id, title, total_chunks, pdf_storage_path, is_global")
        .eq("pdf_hash", pdf_hash)
        .execute()
    )
    return res.data[0] if res.data else None


def upload_pdf_to_storage(content: bytes, slug: str) -> str:
    """Returns '<bucket>/<key>' on success; raises on failure."""
    db = get_db()
    key = slug
    try:
        db.storage.from_(BUCKET).upload(
            path=key,
            file=content,
            file_options={"content-type": "application/pdf", "upsert": "true"},
        )
    except Exception as e:  # noqa: BLE001
        # If `upsert: true` isn't honoured by this storage SDK version, the
        # CLI raises on duplicate. Try remove + upload.
        if "exists" in str(e).lower() or "duplicate" in str(e).lower():
            try:
                db.storage.from_(BUCKET).remove([key])
            except Exception:
                pass
            db.storage.from_(BUCKET).upload(
                path=key,
                file=content,
                file_options={"content-type": "application/pdf"},
            )
        else:
            raise
    return f"{BUCKET}/{key}"


def patch_global_metadata(document_id: str, storage_path: str, page_count: int, size_bytes: int) -> None:
    get_db().table("legal_documents").update(
        {
            "is_global": True,
            "owner_id": None,
            "pdf_storage_path": storage_path,
            "pdf_page_count": page_count,
            "pdf_size_bytes": size_bytes,
        }
    ).eq("id", document_id).execute()


def main() -> int:
    if not INPUT_DIR.exists():
        print(f"INPUT_DIR not found: {INPUT_DIR}")
        return 1

    pdfs = sorted(INPUT_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {INPUT_DIR}")
        return 1

    print(f"Found {len(pdfs)} PDF(s) to ingest.\n")

    summary: list[dict] = []

    for pdf in pdfs:
        print("=" * 78)
        print(f"  {pdf.name}")
        print("=" * 78)

        # ── 1. Hash / dedupe ────────────────────────────────────────
        content = pdf.read_bytes()
        size_bytes = len(content)
        pdf_hash = hashlib.sha256(content).hexdigest()
        existing = pdf_already_ingested(pdf_hash)
        if existing:
            print(f"  Already ingested as document {existing['id']} ({existing['total_chunks']} chunks). Skipping.")
            summary.append({"file": pdf.name, "status": "skipped", "document_id": existing["id"]})
            continue

        # ── 2. Upload to storage ────────────────────────────────────
        slug = slugify(pdf.name)
        print(f"\n  Uploading to storage: {BUCKET}/{slug} ({size_bytes / 1024:.1f} KB)")
        storage_path = upload_pdf_to_storage(content, slug)

        # ── 3. Run ingester ─────────────────────────────────────────
        try:
            res = ingest_pdf(str(pdf))
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR during ingest: {e}")
            summary.append({"file": pdf.name, "status": f"error: {e}"})
            continue

        if res.get("status") != "success":
            print(f"  Ingest returned status={res.get('status')}; not patching as global.")
            summary.append({"file": pdf.name, "status": res.get("status", "?")})
            continue

        document = res["document"]
        document_id = document["id"]

        # ── 4. Patch metadata ───────────────────────────────────────
        try:
            from pypdf import PdfReader
            import io

            page_count = len(PdfReader(io.BytesIO(content)).pages)
        except Exception:
            page_count = 0
        patch_global_metadata(document_id, storage_path, page_count, size_bytes)

        chunks_created = res.get("chunks_created", 0)
        sections = res.get("sections_found", 0)
        pages = res.get("pages_processed", 0)
        print(f"  ✓ ingested: doc {document_id}  pages={pages} sections={sections} chunks={chunks_created}")
        summary.append(
            {
                "file": pdf.name,
                "status": "ingested",
                "document_id": document_id,
                "chunks": chunks_created,
                "pages": pages,
            }
        )

    print()
    print("=" * 78)
    print(" SUMMARY")
    print("=" * 78)
    for s in summary:
        print(f"  {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
