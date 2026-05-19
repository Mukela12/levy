#!/usr/bin/env python3
"""
Batch-ingest every cached Zambian-law PDF discovered by the three research
agents (parliament.gov.zm, zambialii.org, regulators) into the production
global library.

For each PDF in INPUT_DIRS:
  - SKIP if the title contains low-signal patterns (Appropriation Act,
    Supplementary Appropriation, etc.) — these are annual-budget Acts.
  - SKIP if smaller than 50 KB OR fewer than 8 pages — likely an SI,
    amendment, or truncated extract, not the parent Act.
  - SKIP if already ingested (by pdf_hash).
  - UPLOAD to legal-docs storage bucket.
  - RUN the standard ingest pipeline (parse → chunk → OpenAI 768d embed
    → legal_chunks).
  - PATCH the legal_documents row with is_global=true and storage metadata.

Idempotent. Single-threaded so we don't blow past OpenAI's rate limits;
the bottleneck is API latency anyway.
"""

from __future__ import annotations

import hashlib
import io
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from dotenv import load_dotenv

load_dotenv(REPO / "backend" / ".env")

from app.db.supabase import get_db  # noqa: E402
from app.services.ingester import ingest_pdf  # noqa: E402


INPUT_DIRS = [
    Path("/Users/mukelakatungu/levy-test-fixtures/zambian-acts-parliament"),
    Path("/Users/mukelakatungu/levy-test-fixtures/zambian-acts-zambialii"),
    Path("/Users/mukelakatungu/levy-test-fixtures/zambian-regulators"),
]

BUCKET = "legal-docs"

# Filenames whose stem matches one of these patterns are SKIPPED. These are
# the kinds of "Acts" we don't want cluttering the corpus.
SKIP_FILENAME_PATTERNS = [
    re.compile(r"(?i)appropriation", ),
    re.compile(r"(?i)supplementary[_-]appropriation"),
    # Validation/amendment acts that just reference other Acts
    re.compile(r"(?i)^validation[_-]"),
]

MIN_PAGES = 8
MIN_BYTES = 50_000


def slugify(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return base or "doc"


def should_skip(path: Path) -> str | None:
    """Return a reason string if the file should be skipped, else None."""
    stem = path.stem
    for pat in SKIP_FILENAME_PATTERNS:
        if pat.search(stem):
            return f"low-signal filename ({pat.pattern})"
    size = path.stat().st_size
    if size < MIN_BYTES:
        return f"too small ({size} bytes)"
    return None


def existing_doc_by_hash(pdf_hash: str) -> dict | None:
    res = (
        get_db()
        .table("legal_documents")
        .select("id, title, total_chunks, is_global, pdf_storage_path")
        .eq("pdf_hash", pdf_hash)
        .execute()
    )
    return res.data[0] if res.data else None


def page_count_of(content: bytes) -> int:
    try:
        from pypdf import PdfReader
        return len(PdfReader(io.BytesIO(content)).pages)
    except Exception:
        return 0


def upload_pdf_to_storage(content: bytes, slug: str) -> str:
    db = get_db()
    try:
        db.storage.from_(BUCKET).upload(
            path=slug,
            file=content,
            file_options={"content-type": "application/pdf", "upsert": "true"},
        )
    except Exception as e:  # noqa: BLE001
        if "exists" in str(e).lower() or "duplicate" in str(e).lower():
            try:
                db.storage.from_(BUCKET).remove([slug])
            except Exception:
                pass
            db.storage.from_(BUCKET).upload(
                path=slug,
                file=content,
                file_options={"content-type": "application/pdf"},
            )
        else:
            raise
    return f"{BUCKET}/{slug}"


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


def collect_pdfs() -> list[Path]:
    """Walk INPUT_DIRS recursively, return deduplicated list of PDF paths."""
    seen: set[str] = set()
    result: list[Path] = []
    for root in INPUT_DIRS:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*.pdf")):
            key = p.stem.lower()  # dedupe by filename stem across dirs
            if key in seen:
                continue
            seen.add(key)
            result.append(p)
    return result


def main() -> int:
    pdfs = collect_pdfs()
    print(f"Found {len(pdfs)} cached PDF(s) across {len(INPUT_DIRS)} input dirs.\n")

    stats = {"ingested": 0, "skipped-filename": 0, "skipped-tiny": 0, "skipped-pages": 0, "skipped-dupe": 0, "errors": 0}
    failures: list[tuple[Path, str]] = []

    for i, pdf in enumerate(pdfs, 1):
        prefix = f"[{i:4d}/{len(pdfs)}]"
        reason = should_skip(pdf)
        if reason:
            print(f"{prefix} SKIP {pdf.name}: {reason}")
            if "filename" in reason:
                stats["skipped-filename"] += 1
            else:
                stats["skipped-tiny"] += 1
            continue

        content = pdf.read_bytes()
        size_bytes = len(content)
        pages = page_count_of(content)
        if pages and pages < MIN_PAGES:
            print(f"{prefix} SKIP {pdf.name}: too few pages ({pages})")
            stats["skipped-pages"] += 1
            continue

        pdf_hash = hashlib.sha256(content).hexdigest()
        existing = existing_doc_by_hash(pdf_hash)
        if existing:
            # Backfill is_global if needed
            if not existing.get("is_global"):
                get_db().table("legal_documents").update({"is_global": True, "owner_id": None}).eq("id", existing["id"]).execute()
                print(f"{prefix} HAVE {pdf.name}: already ingested as {existing['id'][:8]} (backfilled is_global)")
            else:
                print(f"{prefix} HAVE {pdf.name}: already ingested as {existing['id'][:8]}")
            stats["skipped-dupe"] += 1
            continue

        slug = slugify(pdf.name)
        print(f"{prefix} INGEST {pdf.name} ({size_bytes/1024:.0f} KB, {pages} pages)")
        try:
            storage_path = upload_pdf_to_storage(content, slug)
        except Exception as e:  # noqa: BLE001
            print(f"         storage upload failed: {e}")
            stats["errors"] += 1
            failures.append((pdf, f"storage: {e}"))
            continue

        t0 = time.monotonic()
        try:
            res = ingest_pdf(str(pdf))
        except Exception as e:  # noqa: BLE001
            print(f"         ingest failed: {e}")
            stats["errors"] += 1
            failures.append((pdf, f"ingest: {e}"))
            continue
        elapsed = time.monotonic() - t0

        if res.get("status") != "success":
            print(f"         ingest returned status={res.get('status')}; not patching as global")
            # ingest_pdf creates the legal_documents row BEFORE chunking. If
            # the run came back non-success we'd leave a chunk-less row that
            # the UI would show as an unviewable entry. Delete it so the
            # global library stays clean.
            stale_id = (res.get("document") or {}).get("id")
            if stale_id:
                try:
                    get_db().table("legal_documents").delete().eq("id", stale_id).execute()
                    print(f"         pruned chunkless row {stale_id[:8]}")
                except Exception as e:
                    print(f"         could not prune row: {e}")
            stats["errors"] += 1
            failures.append((pdf, f"status={res.get('status')}"))
            continue

        document = res["document"]
        document_id = document["id"]
        patch_global_metadata(document_id, storage_path, pages, size_bytes)
        chunks = res.get("chunks_created", 0)
        print(f"         ✓ ingested doc={document_id[:8]} chunks={chunks} took={elapsed:.1f}s")
        stats["ingested"] += 1

    print()
    print("=" * 78)
    print(" INGEST SUMMARY")
    print("=" * 78)
    for k, v in stats.items():
        print(f"  {k:>20s} : {v}")
    if failures:
        print(f"\n  {len(failures)} failures:")
        for p, why in failures[:20]:
            print(f"    {p.name}: {why}")
        if len(failures) > 20:
            print(f"    ... and {len(failures) - 20} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
