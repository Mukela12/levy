"""
Ingestion Pipeline — Orchestrates: PDF → Parse → Chunk → Embed → Store

This is the main pipeline for adding new legal documents to the system.
"""

from pathlib import Path
from .parser import parse_legal_pdf, get_pdf_hash
from .chunker import chunk_sections
from .embedder import get_embeddings
from ..db.supabase import (
    insert_document,
    insert_chunks,
    get_document_by_hash,
)


def ingest_pdf(pdf_path: str, force: bool = False) -> dict:
    """
    Full ingestion pipeline for a legal PDF.

    1. Check if already ingested (by PDF hash)
    2. Parse PDF into structured sections
    3. Create metadata-rich chunks
    4. Generate embeddings for all chunks
    5. Store everything in Supabase

    Returns summary of what was ingested.
    """
    pdf_path = str(Path(pdf_path).resolve())
    print(f"\n{'='*60}")
    print(f"INGESTING: {Path(pdf_path).name}")
    print(f"{'='*60}")

    # Step 1: Check for duplicate
    pdf_hash = get_pdf_hash(pdf_path)
    existing = get_document_by_hash(pdf_hash)
    if existing and not force:
        print(f"  Already ingested as: {existing['title']}")
        return {"status": "skipped", "document": existing}

    # Step 2: Parse the PDF
    print("\n[1/4] Parsing PDF...")
    parsed = parse_legal_pdf(pdf_path)
    metadata = parsed["metadata"]

    # Step 3: Insert document record
    print("\n[2/4] Creating document record...")
    doc_record = insert_document({
        "title": metadata.get("title", Path(pdf_path).stem),
        "short_name": metadata.get("short_name", ""),
        "act_number": metadata.get("act_number", ""),
        "year": metadata.get("year"),
        "document_type": "act",
        "pdf_hash": pdf_hash,
        "total_sections": len([s for s in parsed["sections"] if s.level == "section"]),
    })
    document_id = doc_record["id"]
    print(f"  Document ID: {document_id}")

    # Step 4: Create chunks
    print("\n[3/4] Chunking sections...")
    chunks = chunk_sections(parsed["sections"], metadata, document_id)

    if not chunks:
        print("  WARNING: No chunks created. PDF may not have parseable structure.")
        return {"status": "empty", "document": doc_record}

    # Step 5: Generate embeddings
    print("\n[4/4] Generating embeddings...")
    texts = [chunk.content for chunk in chunks]
    embeddings = get_embeddings(texts)

    # Step 6: Store chunks with embeddings
    print("\n  Storing chunks in database...")
    chunk_records = []
    for chunk, embedding in zip(chunks, embeddings):
        chunk_records.append({
            "document_id": chunk.document_id,
            "content": chunk.content,
            "summary": chunk.summary,
            "embedding": embedding,
            "metadata": chunk.metadata,
            "chunk_index": chunk.chunk_index,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
        })

    stored = insert_chunks(chunk_records)

    # Update document with chunk count
    from ..db.supabase import get_db
    get_db().table("legal_documents").update(
        {"total_chunks": len(stored)}
    ).eq("id", document_id).execute()

    summary = {
        "status": "success",
        "document": doc_record,
        "sections_found": len([s for s in parsed["sections"] if s.level == "section"]),
        "parts_found": len([s for s in parsed["sections"] if s.level == "part"]),
        "chunks_created": len(stored),
        "pages_processed": len(parsed["raw_pages"]),
    }

    print(f"\n{'='*60}")
    print(f"INGESTION COMPLETE")
    print(f"  Document: {metadata.get('short_name', '')}")
    print(f"  Sections: {summary['sections_found']}")
    print(f"  Parts: {summary['parts_found']}")
    print(f"  Chunks: {summary['chunks_created']}")
    print(f"  Pages: {summary['pages_processed']}")
    print(f"{'='*60}\n")

    return summary
