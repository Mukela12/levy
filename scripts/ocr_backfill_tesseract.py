#!/usr/bin/env python3
"""Free Tesseract OCR backfill for scanned (header-only) judgments.

The Judiciary publishes most judgments as scanned images, so pdfplumber found
no text and they were ingested as a single title-only header chunk — findable
by case name but not by their reasoning. This promotes them to full text:
OCR each scanned PDF with Tesseract (ocrmypdf --force-ocr), re-chunk, embed,
and replace the header chunk with full-text chunks so precedent search matches
on holdings.

Free alternative to ocr_backfill_judgments.py (which OCRs via Claude, ~$0.18
each). Preserves the original chunk's category + issuing_authority so the
court/area filters in search_case_law keep working.

Idempotency is by total_chunks: a done judgment has >1 chunk so it drops out of
the scanned set; a partial/failed one still has <=1 and is retried. Safe to
re-run. Insert-before-delete so a judgment is never left with zero chunks.

Usage: .../python scripts/ocr_backfill_tesseract.py --limit 200
"""
from __future__ import annotations
import argparse, re, subprocess, sys, tempfile, time, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "scripts"))
import _dns_resilient  # noqa: E402,F401  patch getaddrinfo before any client
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")
from app.db.supabase import get_db, insert_chunks            # noqa: E402
from app.services.embedder import get_embeddings             # noqa: E402


def retry(fn, n=8, d=1.2):
    last = None
    for _ in range(n):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(d)
    raise last


class OcrUnavailable(RuntimeError):
    """ocrmypdf could not run at all, as opposed to a scan it could not read.

    Worth its own type: the first means STOP, every remaining judgment will
    fail the same way; the second means skip this one and carry on.
    """


def ocr_pdf(pdf_bytes: bytes) -> str:
    """OCR a scanned PDF with Tesseract via ocrmypdf; return the sidecar text."""
    with tempfile.TemporaryDirectory() as td:
        ip = Path(td) / "in.pdf"; op = Path(td) / "out.pdf"; side = Path(td) / "t.txt"
        ip.write_bytes(pdf_bytes)
        cmd = [sys.executable, "-m", "ocrmypdf", "--force-ocr", "-l", "eng",
               "--optimize", "0", "--quiet", "--sidecar", str(side), str(ip), str(op)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        # Check the return code. This used to be discarded, so when ocrmypdf
        # was missing from the venv entirely, every judgment came back with an
        # empty sidecar and the script reported "too little text (0)" — which
        # reads as "this scan is unreadable" when the truth was "the OCR tool
        # never ran". Nine Supreme Court judgments were written off that way
        # before anyone looked at the exit code.
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip().splitlines()
            tail = err[-1] if err else f"exit {proc.returncode}"
            raise OcrUnavailable(tail[:160])
        if not side.exists():
            return ""
        return "\n".join(side.read_text(errors="ignore").split("\f"))  # form-feeds -> newlines


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
                chunks.append(p[:hard]); p = p[hard:]
            cur = p
    if cur:
        chunks.append(cur)
    return chunks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    db = get_db()
    rows = retry(lambda: db.table("legal_documents")
                 .select("id,title,short_name,pdf_storage_path,total_chunks")
                 .eq("document_type", "judgment").limit(3000).execute().data) or []
    scanned = [r for r in rows if (r.get("total_chunks") or 0) <= 1 and r.get("pdf_storage_path")]
    print(f"{len(scanned)} scanned judgments to OCR; doing up to {args.limit}", flush=True)

    done = failed = 0
    for r in scanned[: args.limit]:
        did = r["id"]; title = (r.get("title") or "")[:56]
        try:
            ex = retry(lambda: db.table("legal_chunks").select("id,metadata")
                       .eq("document_id", did).execute().data) or []
        except Exception as e:
            print(f"  ! read: {str(e)[:55]} :: {title}", flush=True); failed += 1; continue
        base = (ex[0].get("metadata") if ex else {}) or {}
        citation = r.get("short_name") or base.get("act_name") or title
        old_ids = [c["id"] for c in ex]

        try:
            bucket, _, key = r["pdf_storage_path"].partition("/")
            pdf = retry(lambda: db.storage.from_(bucket).download(key))
        except Exception as e:
            print(f"  ! download: {str(e)[:55]} :: {title}", flush=True); failed += 1; continue

        t0 = time.time()
        try:
            text = ocr_pdf(pdf)
        except subprocess.TimeoutExpired:
            print(f"  ! OCR timeout (>900s) :: {title}", flush=True); failed += 1; continue
        except OcrUnavailable as e:
            # Not this judgment's fault, and the next one will fail identically.
            # Stop rather than marking the whole batch unreadable.
            print(f"\n  !! ocrmypdf could not run: {e}")
            print("  !! Aborting: this is a broken toolchain, not a bad scan.")
            print("  !! Fix with:  backend/.venv/bin/pip install ocrmypdf")
            print(f"\nSUMMARY done={done} failed={failed} aborted=True")
            return 1
        except Exception as e:
            print(f"  ! OCR: {str(e)[:55]} :: {title}", flush=True); failed += 1; continue
        if len(text.strip()) < 500:
            print(f"  ! too little text ({len(text.strip())}) — keeping header :: {title}", flush=True); failed += 1; continue

        pieces = chunk_text(text)
        if not pieces:
            failed += 1; continue
        try:
            embs = retry(lambda: get_embeddings(pieces))
            meta = {"document_type": "judgment", "act_name": citation, "ocr": True, "ocr_engine": "tesseract"}
            if base.get("category"):
                meta["category"] = base["category"]
            if base.get("issuing_authority"):
                meta["issuing_authority"] = base["issuing_authority"]
            recs = [{"document_id": did, "content": t, "embedding": e,
                     "metadata": {**meta, "is_header": i == 0},
                     "chunk_index": i, "page_start": 1, "page_end": 1}
                    for i, (t, e) in enumerate(zip(pieces, embs))]
            # insert first (never leave the doc with zero chunks), then drop old header
            retry(lambda: insert_chunks(recs))
            if old_ids:
                retry(lambda: db.table("legal_chunks").delete().in_("id", old_ids).execute())
            retry(lambda: db.table("legal_documents").update({"total_chunks": len(recs)}).eq("id", did).execute())
            done += 1
            print(f"  [{done}] {len(recs):>3} chunks, {int(time.time()-t0)}s <- {title}", flush=True)
        except Exception as e:
            print(f"  ! store: {str(e)[:70]} :: {title}", flush=True); failed += 1; continue

    print(f"\nSUMMARY done={done} failed={failed}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
