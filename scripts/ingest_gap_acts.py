#!/usr/bin/env python3
"""Ingest the statutes the 2026-07 field study found missing behind the 48%
web-fallback rate. Sourced from the official Parliament of Zambia acts library
(parliament.gov.zm), never ZambiaLII/Zambia Law Reports.

Downloaded + content-verified into scratchpad/acts by the session; this ingests
each as document_type='act' via the same pipeline the rest of the corpus uses,
then marks it global + stores the PDF for download. Re-runnable (skips existing).
"""
import re
import sys
from pathlib import Path

REPO = "/Users/mukelakatungu/levy/.claude/worktrees/gracious-mclean-3f2951"
sys.path.insert(0, REPO + "/backend")
sys.path.insert(0, REPO + "/scripts")
import _dns_resilient  # noqa
from dotenv import load_dotenv
load_dotenv(REPO + "/backend/.env")
from app.db.supabase import get_db
from app.services.form_ingester import ingest_form_pdf
from harvest_judgments_v2 import store, pages_of

ACTS_DIR = Path(REPO + "/scratchpad/acts")
PARL = "https://www.parliament.gov.zm/sites/default/files/documents/acts"

# (filename, title, short_name, description, source_url)
ACTS = [
    ("PenalCode.pdf", "The Penal Code Act", "Penal Code Act (Cap 87)",
     "The Penal Code of Zambia (Chapter 87), the principal criminal statute "
     "defining offences and their penalties.",
     f"{PARL}/Penal%20Code%20Act.pdf"),
    ("CriminalProcedureCode.pdf", "The Criminal Procedure Code Act",
     "Criminal Procedure Code Act (Cap 88)",
     "The Criminal Procedure Code of Zambia (Chapter 88), governing arrest, "
     "bail, trial, appeals and sentencing in criminal matters.",
     f"{PARL}/Criminal%20Procedure%20Code%20Act.pdf"),
    ("RentActCap206.pdf", "The Rent Act", "Rent Act (Cap 206)",
     "The Rent Act of Zambia (Chapter 206), governing rent control, recovery "
     "of rent and distress for rent.",
     f"{PARL}/Rent%20Act.pdf"),
    ("MatrimonialCauses.pdf", "The Matrimonial Causes Act, 2007",
     "Matrimonial Causes Act (No. 20 of 2007)",
     "The Matrimonial Causes Act No. 20 of 2007, governing divorce, nullity, "
     "judicial separation, and financial relief and property on divorce.",
     f"{PARL}/The%20Matrimonial%20Causes%20Act.pdf"),
]


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:70]


def main() -> int:
    db = get_db()
    done = skipped = missing = 0
    for fn, title, short, desc, url in ACTS:
        p = ACTS_DIR / fn
        if not p.exists():
            print(f"  MISSING FILE (not downloaded yet): {fn}", flush=True)
            missing += 1
            continue
        res = ingest_form_pdf(
            str(p), title=title, short_name=short, description=desc,
            document_type="act", category="act",
            issuing_authority="Parliament of Zambia", source_url=url,
        )
        if res.get("status") == "skipped":
            print(f"  skip (already in corpus): {title}", flush=True)
            skipped += 1
            continue
        b = p.read_bytes()
        sp = store(b, _slug(title) + ".pdf")
        doc = res["document"]
        db.table("legal_documents").update({
            "is_global": True, "owner_id": None,
            "pdf_storage_path": sp, "pdf_page_count": pages_of(b),
        }).eq("id", doc["id"]).execute()
        print(f"  INGESTED [act] {title} (chunks={doc.get('total_chunks')}, {len(b)//1024}KB)",
              flush=True)
        done += 1
    print(f"\nDONE  ingested={done} skipped={skipped} missing={missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
