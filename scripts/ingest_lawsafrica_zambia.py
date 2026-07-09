#!/usr/bin/env python3
"""
Ingest Zambian judgments (and optionally legislation) from the Laws.Africa
Content API into Levy's global library — the SANCTIONED, token-authenticated
route to ZambiaLII content (we never scrape ZambiaLII directly).

PREREQUISITES:
  1. A free Laws.Africa account: https://laws.africa  (create it yourself)
  2. Your API token from the account's API profile.
  3. Set it in backend/.env (and on Railway for prod):
         LAWS_AFRICA_API_TOKEN=...

LICENSING: Laws.Africa content is generally CC-BY-NC-SA (non-commercial).
Only run this if Levy's use qualifies as non-commercial OR you hold a
commercial licence from Laws.Africa. The script refuses to run without a
token, and prints this reminder.

Usage:
  /Users/mukelakatungu/levy/.claude/worktrees/lucid-bartik-c2ad7f/.venv/bin/python \
      scripts/ingest_lawsafrica_zambia.py --limit 150 --nature judgment
"""

from __future__ import annotations

import argparse
import io
import sys
import time
import uuid
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from dotenv import load_dotenv

load_dotenv(REPO / "backend" / ".env")

from app.db.supabase import get_db  # noqa: E402
from app.services import laws_africa  # noqa: E402
from app.services.form_ingester import ingest_form_pdf  # noqa: E402

BUCKET = "legal-docs"
DOWNLOAD_DIR = Path("/Users/mukelakatungu/levy-test-fixtures/lawsafrica-zm")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def slugify(name: str) -> str:
    return (re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or uuid.uuid4().hex)[:80]


def upload(content: bytes, slug: str) -> str:
    db = get_db()
    try:
        db.storage.from_(BUCKET).upload(path=slug, file=content,
            file_options={"content-type": "application/pdf", "upsert": "true"})
    except Exception as e:  # noqa: BLE001
        if "exists" in str(e).lower() or "duplicate" in str(e).lower():
            try:
                db.storage.from_(BUCKET).remove([slug])
            except Exception:
                pass
            db.storage.from_(BUCKET).upload(path=slug, file=content,
                file_options={"content-type": "application/pdf"})
        else:
            raise
    return f"{BUCKET}/{slug}"


def page_count(content: bytes) -> int:
    try:
        from pypdf import PdfReader
        return len(PdfReader(io.BytesIO(content)).pages)
    except Exception:
        return 0


def patch_global(doc_id: str, sp: str, pages: int, size: int, url: str, dtype: str) -> None:
    get_db().table("legal_documents").update({
        "is_global": True, "owner_id": None, "pdf_storage_path": sp,
        "pdf_page_count": pages, "pdf_size_bytes": size,
        "canonical_url": url, "document_type": dtype,
    }).eq("id", doc_id).execute()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100, help="max works to ingest")
    ap.add_argument("--nature", default="judgment", choices=["judgment", "act", "all"],
                    help="which works to pull (default judgments)")
    args = ap.parse_args()

    if not laws_africa.is_configured():
        print("LAWS_AFRICA_API_TOKEN is not set in backend/.env.")
        print("Create a free account at https://laws.africa, copy your API")
        print("token from the API profile, and add LAWS_AFRICA_API_TOKEN=... to")
        print("backend/.env (and Railway). Re-run this script after that.")
        print("\nReminder: Laws.Africa content is CC-BY-NC-SA (non-commercial).")
        return 1

    print("Connectivity check:", laws_africa.ping())

    db = get_db()
    ingested = skipped = failed = 0
    seen = 0
    for work in laws_africa.list_works("zm"):
        if ingested >= args.limit:
            break
        nature = (work.get("nature") or "").lower()
        if args.nature != "all" and nature != args.nature:
            continue
        seen += 1
        frbr = work.get("frbr_uri") or work.get("expression_frbr_uri")
        title = (work.get("title") or frbr or "Untitled").strip()
        citation = work.get("numbered_title") or work.get("citation") or None
        if not frbr:
            continue

        print(f"\n[{ingested+1}/{args.limit}] {title[:70]}")
        try:
            pdf = laws_africa.get_work(frbr, fmt="pdf")
        except Exception as e:  # noqa: BLE001
            print(f"   ! fetch failed: {e}")
            failed += 1
            continue
        if not isinstance(pdf, (bytes, bytearray)) or not pdf[:4] == b"%PDF":
            print("   ! not a PDF; skipping")
            failed += 1
            continue

        slug = slugify(title) + ".pdf"
        local = DOWNLOAD_DIR / slug
        local.write_bytes(pdf)

        dtype = "judgment" if nature == "judgment" else "act"
        area = (work.get("taxonomies") or [{}])
        category = nature
        desc = (
            f"{'Zambian court judgment' if dtype=='judgment' else 'Zambian legislation'}"
            + (f" — {citation}." if citation else ".")
            + " Sourced from the Laws.Africa Content API (CC-BY-NC-SA)."
        )
        try:
            res = ingest_form_pdf(
                str(local), title=title, short_name=(citation or title)[:80],
                description=desc, document_type=dtype, category=category,
                issuing_authority="Judiciary of Zambia" if dtype == "judgment" else "Parliament of Zambia",
                source_url=f"https://zambialii.org{frbr}",
            )
        except Exception as e:  # noqa: BLE001
            print(f"   ! ingest error: {e}")
            failed += 1
            continue
        if res["status"] == "skipped":
            skipped += 1
            continue
        try:
            sp = upload(pdf, slug)
            patch_global(res["document"]["id"], sp, page_count(pdf), len(pdf),
                         f"https://zambialii.org{frbr}", dtype)
            print(f"   → {sp}")
        except Exception as e:  # noqa: BLE001
            print(f"   ! storage error: {e}")
            failed += 1
            continue
        ingested += 1
        time.sleep(0.5)

    print(f"\nSUMMARY  seen={seen}  ingested={ingested}  skipped={skipped}  failed={failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
