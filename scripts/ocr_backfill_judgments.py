#!/usr/bin/env python3
"""OCR backfill for scanned (header-only) judgments.

~69% of harvested judgment PDFs are scanned images, so pdfplumber extracted
no text and they were ingested as a single title-only header chunk — findable
by case name but not by their legal reasoning. This script promotes them to
full-text: it sends each scanned PDF to Claude (which OCRs PDFs natively, no
poppler/tesseract needed), re-chunks the extracted text, embeds it, and
replaces the doc's chunks so precedent search matches on holdings.

Targets judgments with total_chunks <= 1. Idempotent: skips ones already OCR'd
(chunks flagged ocr=True). Run with --limit N to batch.

Usage:
  .../python scripts/ocr_backfill_judgments.py --limit 62
"""
from __future__ import annotations
import argparse, base64, os, re, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")

import anthropic
from app.db.supabase import get_db, insert_chunks            # noqa: E402
from app.services.embedder import get_embeddings             # noqa: E402

MODEL = "claude-sonnet-4-6"
EXTRACT_PROMPT = (
    "This is a Zambian court judgment (scanned). Extract the full text "
    "verbatim as plain text: parties, coram, the body of the judgment, the "
    "court's reasoning, and the holding/orders. Preserve paragraph breaks. "
    "Do not summarise, comment, or add anything — output only the judgment text."
)


def chunk_text(text: str, target: int = 1100) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    cur = ""
    hard = int(target * 1.4)
    for p in paras:
        if len(cur) + len(p) <= hard:
            cur = (cur + "\n\n" + p).strip()
        else:
            if cur:
                chunks.append(cur)
            while len(p) > int(target * 1.6):
                chunks.append(p[:hard])
                p = p[hard:]
            cur = p
    if cur:
        chunks.append(cur)
    return chunks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=62)
    args = ap.parse_args()

    db = get_db()
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=600.0, max_retries=2)

    rows = (db.table("legal_documents")
            .select("id,title,short_name,pdf_storage_path,total_chunks")
            .eq("document_type", "judgment").execute().data or [])
    scanned = [r for r in rows if (r.get("total_chunks") or 0) <= 1 and r.get("pdf_storage_path")]
    print(f"{len(scanned)} scanned judgments to OCR; doing {min(args.limit, len(scanned))}")

    done = failed = 0
    for r in scanned[: args.limit]:
        did, title = r["id"], (r.get("title") or "")[:60]
        # already OCR'd? (chunk flagged)
        try:
            ex = db.table("legal_chunks").select("id,metadata").eq("document_id", did).execute().data or []
            if any((c.get("metadata") or {}).get("ocr") for c in ex):
                continue
        except Exception:
            ex = []
        # fetch the PDF
        try:
            bucket, _, key = r["pdf_storage_path"].partition("/")
            pdf = db.storage.from_(bucket).download(key)
            b64 = base64.standard_b64encode(pdf).decode()
        except Exception as e:
            print(f"  ! fetch: {e} :: {title}"); failed += 1; continue
        # OCR via Claude
        try:
            msg = client.messages.create(
                model=MODEL, max_tokens=16000,
                messages=[{"role": "user", "content": [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
                    {"type": "text", "text": EXTRACT_PROMPT},
                ]}],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        except Exception as e:
            print(f"  ! ocr: {str(e)[:80]} :: {title}"); failed += 1; continue
        if len(text) < 500:
            print(f"  ! too little text ({len(text)}) :: {title}"); failed += 1; continue

        pieces = chunk_text(text)
        if not pieces:
            failed += 1; continue
        try:
            embeddings = get_embeddings(pieces)
            citation = r.get("short_name") or title
            # delete the old header-only chunk(s), insert OCR chunks
            db.table("legal_chunks").delete().eq("document_id", did).execute()
            recs = []
            for i, (txt, emb) in enumerate(zip(pieces, embeddings)):
                recs.append({
                    "document_id": did, "content": txt, "embedding": emb,
                    "metadata": {"act_name": citation, "document_type": "judgment", "ocr": True},
                    "chunk_index": i, "page_start": 1, "page_end": 1,
                })
            insert_chunks(recs)
            db.table("legal_documents").update({"total_chunks": len(recs)}).eq("id", did).execute()
            done += 1
            print(f"  [{done}] {len(recs)} chunks <- {title}")
        except Exception as e:
            print(f"  ! store: {str(e)[:80]} :: {title}"); failed += 1; continue
        time.sleep(0.3)

    print(f"\nSUMMARY done={done} failed={failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
