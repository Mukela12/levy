#!/usr/bin/env python3
"""
CLI script to ingest a legal PDF into Levy's database.

Usage:
    python scripts/ingest_pdf.py data/pdfs/employment_code.pdf
    python scripts/ingest_pdf.py data/pdfs/ --all        # ingest all PDFs in directory
    python scripts/ingest_pdf.py data/pdfs/file.pdf --force  # re-ingest even if exists
"""

import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

from app.services.ingester import ingest_pdf


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/ingest_pdf.py <pdf_path> [--all] [--force]")
        sys.exit(1)

    target = sys.argv[1]
    force = "--force" in sys.argv
    ingest_all = "--all" in sys.argv

    if ingest_all and Path(target).is_dir():
        pdfs = sorted(Path(target).glob("*.pdf"))
        print(f"Found {len(pdfs)} PDFs to ingest\n")
        for pdf in pdfs:
            try:
                result = ingest_pdf(str(pdf), force=force)
                print(f"  -> {result['status']}\n")
            except Exception as e:
                print(f"  -> ERROR: {e}\n")
    else:
        if not Path(target).exists():
            print(f"File not found: {target}")
            sys.exit(1)
        result = ingest_pdf(target, force=force)
        print(f"\nResult: {result['status']}")


if __name__ == "__main__":
    main()
