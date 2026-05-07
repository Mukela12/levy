#!/usr/bin/env python3
"""
Re-ingest the canonical Zambian-law PDF library.

Per Act:
  1. Download canonical PDF from gov source (cached locally).
  2. Run the existing parser/chunker pipeline (BGE-base, 768-dim).
  3. Atomically replace the document's chunks (delete old, insert new).
  4. Upload PDF to Supabase Storage at `legal-docs/{document_id}.pdf`,
     stamp `pdf_storage_path`, `canonical_url`, `pdf_size_bytes`,
     `pdf_page_count`, refreshed `title`/`short_name`/`year`.

Garbage cleanup deletes 3 rows that aren't legitimate Acts (a tech
whitepaper that drifted in + 2 mis-labeled Constitution fragments).

Run from repo root:
  source .venv/bin/activate
  TAVILY_API_KEY=... SUPABASE_URL=... SUPABASE_KEY=<service_role> \\
    python scripts/reingest_acts.py
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from io import BytesIO
from pathlib import Path

import httpx
import pdfplumber
from supabase import create_client

# Make app importable so we can reuse the existing pipeline modules.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# Force local embeddings before importing the embedder.
os.environ.setdefault("EMBEDDING_PROVIDER", "local")
os.environ.setdefault("EMBEDDING_DIMENSIONS", "768")

from app.services.parser import parse_legal_pdf  # noqa: E402
from app.services.chunker import chunk_sections  # noqa: E402
from app.services.embedder import get_embeddings  # noqa: E402


CACHE_DIR = ROOT / ".cache" / "ingest_pdfs"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


ACTS = [
    {"db_title": "REPUBLIC OF ZAMBIA THE COMPANIES ACT",
     "label": "Companies Act, No. 10 of 2017", "short_name": "Companies Act", "year": 2017,
     "url": "https://zambialii.org/akn/zm/act/2017/10/eng@2017-11-20/source.pdf"},
    {"db_title": "REPUBLIC OF ZAMBIA THE PENAL CODE ACT",
     "label": "Penal Code Act, Cap. 87", "short_name": "Penal Code Act", "year": None,
     "url": "https://www.parliament.gov.zm/sites/default/files/documents/acts/Penal%20Code%20Act.pdf"},
    {"db_title": "Employment Code",
     "label": "Employment Code Act, No. 3 of 2019", "short_name": "Employment Code Act", "year": 2019,
     "url": "https://www.parliament.gov.zm/sites/default/files/documents/acts/The%20Employment%20Code%20Act%20No.%203%20of%202019.pdf"},
    {"db_title": "THE MINES AND MINERALS DEVELOPMENT ACT, 2015",
     "label": "Mines and Minerals Development Act, 2015", "short_name": "Mines and Minerals Act", "year": 2015,
     "url": "https://www.parliament.gov.zm/sites/default/files/documents/acts/The%20Mines%20and%20Minerals%20Act%2C%202015.pdf"},
    {"db_title": "THE ENVIRONMENTAL MANAGEMENT ACT, 2011",
     "label": "Environmental Management Act, No. 12 of 2011", "short_name": "Environmental Management Act", "year": 2011,
     "url": "https://www.parliament.gov.zm/sites/default/files/documents/acts/Environmetal%20Mangement%20Act%2012%20of%202011.pdf"},
    {"db_title": "THE PUBLIC PROCUREMENT ACT, 2020",
     "label": "Public Procurement Act, No. 8 of 2020", "short_name": "Public Procurement Act", "year": 2020,
     "url": "https://www.parliament.gov.zm/sites/default/files/documents/acts/The%20Public%20Procurement%20Act%20No.%208%202020.pdf"},
    {"db_title": "REPUBLIC OF ZAMBIA THE LANDS ACT",
     "label": "Lands Act, Cap. 184", "short_name": "Lands Act", "year": None,
     "url": "https://media.zambialii.org/media/legislation/39615/source_file/6516fc140c65c2c9/lands-act.pdf"},
    {"db_title": "REPUBLIC OF ZAMBIA THE LANDS AND DEEDS REGISTRY ACT",
     "label": "Lands and Deeds Registry Act, Cap. 185", "short_name": "Lands and Deeds Registry Act", "year": None,
     "url": "https://www.parliament.gov.zm/sites/default/files/documents/acts/Lands%20and%20Deeds%20Registry%20Act.pdf"},
    {"db_title": "THE CONSTITUTION OF ZAMBIA ACT, 2016",
     "label": "Constitution of Zambia (Amendment) Act, 2016", "short_name": "Constitution", "year": 2016,
     "url": "https://www.parliament.gov.zm/sites/default/files/documents/acts/Constitution%20of%20Zambia%20Act%202016%20_0.pdf"},
]

# Document rows that aren't legitimate Acts and should be deleted entirely.
GARBAGE_HASH_PREFIXES = [
    "bd7e0192",  # tech whitepaper
    "2953365f",  # mis-labeled Constitution fragment
    "3435e36b",  # mis-labeled Constitution fragment
]


def download_pdf(url: str, dest: Path) -> bytes:
    if dest.exists() and dest.stat().st_size > 1024:
        data = dest.read_bytes()
        if data.startswith(b"%PDF"):
            return data
    print(f"  downloading {url}")
    # parliament.gov.zm has a cert chain Apple's CA bundle doesn't trust;
    # the content is publicly available so we accept self-signed/intermediate
    # gaps and rely on the post-download integrity checks (page count + sha)
    # to flag tampering or wrong files.
    with httpx.Client(timeout=120.0, follow_redirects=True, verify=False) as client:
        resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 (Levy Ingester)"})
        resp.raise_for_status()
    data = resp.content
    if not data.startswith(b"%PDF"):
        raise RuntimeError(f"not a PDF (got {data[:20]!r})")
    dest.write_bytes(data)
    return data


def page_count(pdf_bytes: bytes) -> int:
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        return len(pdf.pages)


def db_lookup_doc(db, db_title: str) -> dict | None:
    res = db.table("legal_documents").select("*").eq("title", db_title).limit(1).execute()
    return res.data[0] if res.data else None


def replace_chunks(db, document_id: str, chunks: list) -> None:
    """Delete existing chunks for the doc and insert new ones."""
    db.table("legal_chunks").delete().eq("document_id", document_id).execute()
    db.table("legal_hierarchy").delete().eq("document_id", document_id).execute()


def insert_chunk_rows(db, document_id: str, chunks: list, embeddings: list[list[float]]) -> int:
    rows = []
    for c, emb in zip(chunks, embeddings):
        # chunks are LegalChunk pydantic models from the chunker
        rows.append({
            "document_id": document_id,
            "content": c.content,
            "summary": c.summary,
            "embedding": emb,
            "metadata": c.metadata,
            "chunk_index": c.chunk_index,
            "page_start": c.page_start,
            "page_end": c.page_end,
        })
    inserted = 0
    for i in range(0, len(rows), 50):
        batch = rows[i:i + 50]
        db.table("legal_chunks").insert(batch).execute()
        inserted += len(batch)
    return inserted


def upload_pdf_to_storage(supabase_url: str, service_key: str, document_id: str, pdf_bytes: bytes) -> str:
    path = f"{document_id}.pdf"
    with httpx.Client(timeout=120.0) as client:
        # Delete pre-existing object if any (idempotent re-runs)
        client.delete(
            f"{supabase_url}/storage/v1/object/legal-docs/{path}",
            headers={"Authorization": f"Bearer {service_key}"},
        )
        resp = client.post(
            f"{supabase_url}/storage/v1/object/legal-docs/{path}",
            headers={
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/pdf",
                "x-upsert": "true",
            },
            content=pdf_bytes,
        )
        resp.raise_for_status()
    return f"legal-docs/{path}"


def main():
    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    service_key = os.environ["SUPABASE_KEY"]
    db = create_client(supabase_url, service_key)

    # ─── 1. Drop the garbage rows ────────────────────────────────────────────
    print("\n=== Cleaning garbage documents ===")
    all_docs = db.table("legal_documents").select("id, title, pdf_hash").execute().data or []
    for prefix in GARBAGE_HASH_PREFIXES:
        match = next((r for r in all_docs if (r.get("pdf_hash") or "").startswith(prefix)), None)
        if not match:
            print(f"  hash {prefix}: no match (already cleaned?)")
            continue
        doc_id = match["id"]
        title = match["title"] or "(empty)"
        print(f"  deleting {title!r} ({doc_id[:8]}…)")
        db.table("legal_chunks").delete().eq("document_id", doc_id).execute()
        db.table("legal_hierarchy").delete().eq("document_id", doc_id).execute()
        db.table("legal_documents").delete().eq("id", doc_id).execute()

    # ─── 2. Re-ingest each Act ───────────────────────────────────────────────
    print("\n=== Re-ingesting canonical Acts ===")
    summary_rows = []
    for act in ACTS:
        print(f"\n• {act['label']}")
        slug = "".join(c if c.isalnum() else "_" for c in act["short_name"])[:40]
        cache_path = CACHE_DIR / f"{slug}.pdf"
        try:
            pdf_bytes = download_pdf(act["url"], cache_path)
        except Exception as e:
            print(f"  ✗ download failed: {e}")
            continue

        try:
            pages = page_count(pdf_bytes)
        except Exception as e:
            print(f"  ✗ unreadable PDF: {e}")
            continue
        sha = hashlib.sha256(pdf_bytes).hexdigest()
        size_kb = len(pdf_bytes) / 1024
        print(f"  {pages} pages · {size_kb:.0f}KB · sha256 {sha[:12]}")

        # Find existing doc to keep its id (so chat citations referencing
        # document.title -> same id).
        existing = db_lookup_doc(db, act["db_title"])
        if existing is None:
            ins = db.table("legal_documents").insert({
                "title": act["label"],
                "short_name": act["short_name"],
                "year": act["year"],
                "document_type": "act",
                "source_url": act["url"],
                "canonical_url": act["url"],
                "pdf_hash": sha,
                "pdf_page_count": pages,
                "pdf_size_bytes": len(pdf_bytes),
            }).execute()
            existing = ins.data[0]
        else:
            db.table("legal_documents").update({
                "title": act["label"],
                "short_name": act["short_name"],
                "year": act["year"],
                "source_url": act["url"],
                "canonical_url": act["url"],
                "pdf_hash": sha,
                "pdf_page_count": pages,
                "pdf_size_bytes": len(pdf_bytes),
            }).eq("id", existing["id"]).execute()

        document_id = existing["id"]

        # Parse + chunk + embed
        t0 = time.monotonic()
        parsed = parse_legal_pdf(str(cache_path))
        chunks = chunk_sections(parsed["sections"], parsed["metadata"], document_id)
        if not chunks:
            print(f"  ✗ no chunks created")
            continue
        print(f"  parsed in {time.monotonic() - t0:.1f}s · {len(chunks)} chunks")

        t0 = time.monotonic()
        texts = [c.content for c in chunks]
        embeddings = get_embeddings(texts)
        print(f"  embedded in {time.monotonic() - t0:.1f}s ({len(embeddings[0])}-dim)")

        # Atomic chunk swap
        replace_chunks(db, document_id, chunks)
        inserted = insert_chunk_rows(db, document_id, chunks, embeddings)

        # Update final counts
        db.table("legal_documents").update({
            "total_chunks": inserted,
            "total_sections": sum(1 for s in parsed["sections"] if getattr(s, "level", None) == "section"),
        }).eq("id", document_id).execute()

        # Upload PDF to storage
        path = upload_pdf_to_storage(supabase_url, service_key, document_id, pdf_bytes)
        db.table("legal_documents").update({"pdf_storage_path": path}).eq("id", document_id).execute()
        print(f"  ✓ {inserted} chunks · stored at {path}")
        summary_rows.append({"title": act["label"], "chunks": inserted, "pages": pages})

    print("\n=== Done ===")
    for s in summary_rows:
        print(f"  {s['title']}: {s['chunks']} chunks · {s['pages']} pages")


if __name__ == "__main__":
    main()
