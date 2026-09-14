#!/usr/bin/env python3
"""Second pass for the Acts the parliament harvest queued as scans.

Downloads each queued PDF, OCRs it with tesseract (pdftoppm -> tesseract pdf
-> merged with pypdf; ocrmypdf is broken on this Mac), and ingests the
searchable copy with the listing's title, the same way the harvester does.
  OPENAI_API_KEY=<harvest key> python scripts/ingest_needs_ocr.py --queue scripts/needs_ocr.txt --work <dir>
"""
from __future__ import annotations
import argparse, re, subprocess, sys, tempfile, glob
from pathlib import Path
import httpx
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend")); sys.path.insert(0, str(REPO / "scripts"))
import _dns_resilient  # noqa: F401
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")
from app.db.supabase import get_db  # noqa: E402
from app.services.ingester import ingest_pdf  # noqa: E402
from harvest_judgments_v2 import store, pages_of  # noqa: E402
from harvest_parliament_acts import parse_entry, norm, held_keys  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402


def ocr(src: Path, dst: Path) -> None:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-r", "220", "-png", str(src), f"{td}/p"], check=True)
        for img in sorted(glob.glob(f"{td}/p-*.png")):
            subprocess.run(["tesseract", img, img[:-4], "-l", "eng", "pdf"], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        w = PdfWriter()
        for f in sorted(glob.glob(f"{td}/p-*.pdf")):
            for pg in PdfReader(f).pages:
                w.add_page(pg)
        with open(dst, "wb") as fh:
            w.write(fh)


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--queue", required=True); ap.add_argument("--work", required=True)
    args = ap.parse_args(); work = Path(args.work); work.mkdir(parents=True, exist_ok=True)
    db = get_db(); held = held_keys(db)
    seen = set(); done = skipped = failed = 0
    for line in Path(args.queue).read_text().splitlines():
        node, title, url, pages = line.split("|")
        if node in seen: continue
        seen.add(node)
        e = parse_entry({"node": node, "title": title, "no": ""})
        if norm(e["title"]) in held:
            print(f"  held: {e['title']}"); skipped += 1; continue
        try:
            raw = work / (re.sub(r"[^A-Za-z0-9]+", "_", e["title"]).strip("_")[:70] + ".raw.pdf")
            if not raw.exists():
                with httpx.Client(timeout=120, follow_redirects=True, verify=False, headers={"User-Agent": "Mozilla/5.0"}) as c:
                    raw.write_bytes(c.get(url).content)
            out = raw.with_suffix("").with_suffix(".ocr.pdf")
            if not out.exists():
                ocr(raw, out)
            body = out.read_bytes()
            text = sum(len((p.extract_text() or "").strip()) for p in PdfReader(out).pages[:3])
            if text < 200:
                print(f"  OCR produced no text: {e['title']}"); failed += 1; continue
            res = ingest_pdf(str(out), overrides={"title": e["title"], "short_name": e["short"], "year": e["year"]})
            if res.get("status") == "skipped":
                skipped += 1; continue
            doc = res["document"]
            sp = store(raw.read_bytes(), raw.name.replace(".raw", ""))  # the original scan is what users open
            db.table("legal_documents").update({"title": e["title"], "short_name": e["short"], "year": e["year"],
                "is_global": True, "owner_id": None, "pdf_storage_path": sp, "pdf_page_count": pages_of(body),
                "pdf_size_bytes": len(body), "canonical_url": url, "source_url": url}).eq("id", doc["id"]).execute()
            print(f"  INGESTED (OCR) {e['title']} chunks={res.get('chunks_created')}", flush=True); done += 1
        except Exception as ex:  # noqa: BLE001
            print(f"  FAILED {e['title']}: {type(ex).__name__}: {str(ex)[:120]}", flush=True); failed += 1
    print(f"\nDONE ingested={done} skipped={skipped} failed={failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
