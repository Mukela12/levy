#!/usr/bin/env python3
"""OCR (free, local Tesseract via ocrmypdf) + ingest the UNZA School of Law
past papers into the Levy corpus as global practice material.

These are University of Zambia LLB past papers from the open-access repository
(dspace.unza.zm). They are NOT ZIALE bar (LPQE) papers; they are labelled
honestly as UNZA papers (document_type='past_paper') so Study Mode never
passes a university paper off as a bar paper.

Two guards, because the source filenames are NOT reliable:
  1. Every file is a scanned image, so we add a text layer with ocrmypdf
     first (no Anthropic credits), then run the normal ingest pipeline.
  2. After OCR we CHECK the content is actually law (one grabbed file turned
     out to be a Library Studies paper). Non-law papers are skipped.

Run with the working venv python so `-m ocrmypdf` uses a healthy pyexpat:
  .../lucid-bartik-c2ad7f/.venv/bin/python scripts/ingest_unza_past_papers.py
"""
from __future__ import annotations
import io, os, re, subprocess, sys, tempfile
from pathlib import Path

REPO = Path("/Users/mukelakatungu/levy/.claude/worktrees/gracious-mclean-3f2951")
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "scripts"))
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")
from app.services.ingester import ingest_pdf            # noqa: E402
from app.db.supabase import get_db                       # noqa: E402
import scrape_and_ingest_zambian_acts as base            # noqa: E402
from pypdf import PdfReader                               # noqa: E402
import pdfplumber                                         # noqa: E402

SRC_DIR = Path("/Users/mukelakatungu/ziale-past-papers")
SOURCE_URL = "https://dspace.unza.zm"
BREW_PATH = "/opt/homebrew/bin:" + os.environ.get("PATH", "")

LAW_TERMS = [
    "school of law", "llb", "bachelor of laws", "law of contract", "criminal law",
    "constitutional law", "law of tort", "jurisprudence", "civil procedure",
    "criminal procedure", "land law", "family law", "succession", "commercial law",
    "administrative law", "human rights", "company law", "legal", "plaintiff",
    "defendant", "appellant", "statute", "moot", "equity", "trusts", "evidence",
]
NONLAW_TERMS = [
    "school of education", "library studies", "school of medicine", "school of nursing",
    "school of natural sciences", "school of engineering", "department of library",
    "research methods in library", "nursing", "biology", "chemistry", "physics",
    "school of agriculture", "veterinary", "school of mines",
]


def year_label(stem: str) -> str:
    s = stem.replace("UNZA-Law-PastPapers-", "")
    s = s.replace("set1", "(Set 1)").replace("set2", "(Set 2)").replace("deferred", "(Deferred)")
    s = re.sub(r"(\d{4})-(\d{4})", r"\1/\2", s)
    return re.sub(r"\s+", " ", s.replace("-", " ")).strip()


def ocr_pdf(src: Path, dst: Path) -> bool:
    try:
        subprocess.run(
            [sys.executable, "-m", "ocrmypdf", "--force-ocr", "--output-type", "pdf",
             "-l", "eng", "--jobs", "4", "--quiet", str(src), str(dst)],
            check=True, capture_output=True, timeout=1200,
            env={**os.environ, "PATH": BREW_PATH},
        )
        return dst.exists() and dst.stat().st_size > 0
    except Exception as e:  # noqa: BLE001
        err = getattr(e, "stderr", b"") or b""
        print(f"    ocr error: {err[:160].decode(errors='ignore') or str(e)[:120]}")
        return False


def extract_text(pdf_path: Path) -> str:
    out = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for pg in pdf.pages:
            out.append(pg.extract_text() or "")
    return "\n".join(out)


def is_law(text: str) -> tuple[bool, int, int]:
    t = text.lower()
    law = sum(t.count(k) for k in LAW_TERMS)
    nonlaw = sum(t.count(k) for k in NONLAW_TERMS)
    return (law >= 4 and law > nonlaw * 2, law, nonlaw)


def main() -> int:
    pdfs = sorted(SRC_DIR.glob("UNZA-Law-PastPapers-*.pdf"))
    print(f"found {len(pdfs)} files to OCR + verify + ingest\n")
    ingested = skipped_nonlaw = failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for p in pdfs:
            yl = year_label(p.stem)
            print(f"-> {p.name}  ({yl})")
            ocr_path = Path(tmp) / (p.stem + "-ocr.pdf")
            if not ocr_pdf(p, ocr_path):
                failed += 1
                continue
            text = extract_text(ocr_path)
            law, ls, nls = is_law(text)
            if not law:
                skipped_nonlaw += 1
                snippet = re.sub(r"\s+", " ", text[:120]).strip()
                print(f"    SKIP (not law: law={ls} nonlaw={nls}) :: {snippet}")
                continue
            content = ocr_path.read_bytes()
            try:
                pages = len(PdfReader(io.BytesIO(content)).pages)
            except Exception:
                pages = None
            res = ingest_pdf(str(ocr_path), force=True)
            if res.get("status") != "success":
                print(f"    ingest status={res.get('status')}")
                failed += 1
                continue
            doc_id = (res.get("document") or {}).get("id")
            title = f"UNZA School of Law Past Paper {yl}"
            slug = base.slugify(title) + ".pdf"
            sp = base.upload_pdf_to_storage(content, slug)
            base.patch_global_metadata(doc_id, sp, pages, len(content), SOURCE_URL)
            get_db().table("legal_documents").update({
                "title": title,
                "short_name": f"UNZA Law Past Paper {yl}",
                "document_type": "past_paper",
            }).eq("id", doc_id).execute()
            ingested += 1
            print(f"    INGESTED (law={ls} nonlaw={nls}): {pages}p, {res.get('chunks_created')} chunks, global")

    print(f"\nDONE: ingested={ingested}  skipped_nonlaw={skipped_nonlaw}  failed={failed}  total={len(pdfs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
