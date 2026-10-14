#!/usr/bin/env python3
"""Ingest judgment PDFs that prefetch_judgment_pdfs.py downloaded but the
court archives no longer list.

The Judiciary re-uploaded many older judgments in February 2026, and some
posts are reachable only through older links, so harvest_court_decisions.py
(which walks the archives) never meets them. This takes an explicit list of
PDF URLs, already checked against the library for duplicates, and ingests each
from scripts/.pdf_cache/ exactly as the harvester does: text layer, or OCR
with page numbers, the court from the citation or the bench, the PDF stored.
A court the citation and bench cannot settle is left as "Judiciary of Zambia"
rather than guessed: a wrong court misstates precedent weight.

  backend/.venv/bin/python scripts/with_harvest_key.py scripts/ingest_cached_judgments.py --list URLS.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harvest_court_decisions as hcd  # noqa: E402

UNKNOWN_COURT = "Judiciary of Zambia"


def ingest_one(pdf: str, have: set[str]) -> str:
    if pdf in have:
        return "skip: already held"
    path = hcd.cached_pdf_path(pdf)
    if not path.is_file():
        return "skip: not downloaded"
    content = path.read_bytes()
    if not content.startswith(b"%PDF") or len(content) < 20_000:
        return "skip: not a usable PDF"
    title, citation = hcd.derive(pdf, b"")
    if not hcd.looks_like_judgment(pdf, title):
        return "skip: not a judgment"
    court, how = hcd.court_of(pdf, title, UNKNOWN_COURT)
    area = hcd.infer_area(title)
    key = hcd.slug(title) + ".pdf"
    local = hcd.DOWNLOAD_DIR / key
    local.write_bytes(content)
    desc = (f"Zambian court judgment ({area} law) decided by the {court}."
            + (f" Citation: {citation}." if citation else "") + " Published by the Judiciary of Zambia.")
    res = hcd.ingest_form_pdf(str(local), title=title, short_name=(citation or title)[:80], description=desc,
                              document_type="judgment", category=area, issuing_authority=court,
                              source_url=pdf, ocr_follows=True)
    if res["status"] == "skipped":
        return "skip: ingester skipped it"
    doc_id = res["document"]["id"]
    db = hcd.get_db()
    db.table("legal_documents").update({"is_global": True, "owner_id": None, "canonical_url": pdf,
                                        "document_type": "judgment"}).eq("id", doc_id).execute()
    stored = True
    try:
        sp = hcd.upload(content, key)
        db.table("legal_documents").update({"pdf_storage_path": sp, "pdf_page_count": hcd.pages_of(content),
                                            "pdf_size_bytes": len(content)}).eq("id", doc_id).execute()
    except Exception as e:  # noqa: BLE001  linked instead, as the harvester does
        stored = False
        print(f"    ~ pdf store skipped (linked instead): {str(e)[:50]}")
    have.add(pdf)
    note = f"[{court.replace(' of Zambia', '')}, by {how}]"
    if (res.get("chunks_created") or 0) <= 1:
        # Read from the local copy when the upload was refused (too large).
        ok, detail = hcd.promote_scanned(doc_id, title=title[:56], pdf_bytes=None if stored else content)
        note += f" OCR:{detail}" if ok else f" OCR failed:{detail}"
    return f"ingested {note}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True, help="file of PDF URLs, one per line")
    args = ap.parse_args()
    if problem := hcd.ocr_preflight():
        print(f"!! OCR toolchain unavailable: {problem}")
        return 1
    urls = [u.strip() for u in Path(args.list).read_text().splitlines() if u.strip()]
    have = hcd.already()
    done = 0
    for i, pdf in enumerate(urls, 1):
        try:
            result = ingest_one(pdf, have)
        except hcd.OcrUnavailable as e:
            print(f"!! ocrmypdf stopped working: {e}. Stopping.")
            return 1
        except Exception as e:  # noqa: BLE001
            result = f"failed: {str(e)[:80]}"
        done += result.startswith("ingested")
        print(f"[{i}/{len(urls)}] {result}  {hcd.derive(pdf, b'')[0][:60]}", flush=True)
    print(f"SUMMARY ingested={done} of {len(urls)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
