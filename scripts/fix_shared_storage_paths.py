#!/usr/bin/env python3
"""Give every library document its own stored PDF.

ingest_global_library.py and the forms scraper used to key uploads by file
name with upsert, so documents whose files shared a name ("The
Appropriation.pdf") shared one storage object, and all but the last opened
somebody else's PDF. The database still holds each document's true
`pdf_hash`, so the right file can be recovered and proved.

For every storage path used by documents with different hashes:
  * the document whose hash matches the object already stored keeps it;
  * any other document is fixed only when its own source_url/canonical_url
    serves a PDF whose sha256 equals its recorded pdf_hash. That file is
    uploaded to legal-docs/library/<document id>.pdf and the row repointed.
Anything that cannot be proved is reported and left alone.

  backend/.venv/bin/python scripts/fix_shared_storage_paths.py            # report
  backend/.venv/bin/python scripts/fix_shared_storage_paths.py --apply    # upload + repoint
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
import time
import warnings
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / "backend" / ".env")
from app.db.supabase import get_db  # noqa: E402

warnings.filterwarnings("ignore")
UA = {"User-Agent": "Mozilla/5.0 (Levy legal library; storage integrity repair)"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--save-dir", type=Path, help="keep downloaded PDFs here (id.pdf)")
    args = ap.parse_args()
    db = get_db()

    docs, start = [], 0
    while True:
        rows = (db.table("legal_documents")
                .select("id,title,pdf_storage_path,pdf_hash,source_url,canonical_url")
                .not_.is_("pdf_storage_path", "null").range(start, start + 999).execute().data)
        docs += rows
        if len(rows) < 1000:
            break
        start += 1000
    by_path = collections.defaultdict(list)
    for d in docs:
        by_path[d["pdf_storage_path"]].append(d)
    conflicts = {p: v for p, v in by_path.items() if len({d["pdf_hash"] for d in v}) > 1}
    print(f"{len(conflicts)} shared paths, {sum(len(v) for v in conflicts.values())} documents")

    client = httpx.Client(timeout=90, follow_redirects=True, verify=False, headers=UA)
    report = []
    for path, group in conflicts.items():
        bucket, _, key = path.partition("/")
        try:
            stored_hash = hashlib.sha256(db.storage.from_(bucket).download(key)).hexdigest()
        except Exception:  # noqa: BLE001
            stored_hash = None
        for d in group:
            row = {"id": d["id"], "title": d["title"], "path": path}
            if d["pdf_hash"] == stored_hash:
                row["result"] = "owns the stored file"
                report.append(row)
                continue
            body = None
            for url in (d.get("source_url"), d.get("canonical_url")):
                if not url or not url.startswith("http"):
                    continue
                try:
                    r = client.get(url)
                    time.sleep(1.2)
                except Exception:  # noqa: BLE001
                    continue
                if r.status_code == 200 and r.content[:5].startswith(b"%PDF") \
                        and hashlib.sha256(r.content).hexdigest() == d["pdf_hash"]:
                    body = r.content
                    row["url"] = url
                    break
            if body is None:
                row["result"] = "UNPROVEN: no official copy matching its recorded hash"
                report.append(row)
                continue
            if args.save_dir:
                args.save_dir.mkdir(parents=True, exist_ok=True)
                (args.save_dir / f"{d['id']}.pdf").write_bytes(body)
            new_key = f"library/{d['id']}.pdf"
            if args.apply:
                try:
                    db.storage.from_("legal-docs").upload(
                        new_key, body, file_options={"content-type": "application/pdf", "upsert": "false"})
                except Exception as exc:  # noqa: BLE001
                    if "exist" not in str(exc).lower() and "duplicate" not in str(exc).lower():
                        raise
                back = db.storage.from_("legal-docs").download(new_key)
                if hashlib.sha256(back).hexdigest() != d["pdf_hash"]:
                    raise RuntimeError(f"{d['id']}: uploaded object does not match its hash")
                db.table("legal_documents").update({"pdf_storage_path": f"legal-docs/{new_key}"}).eq("id", d["id"]).execute()
                row["result"] = f"repointed to legal-docs/{new_key}"
            else:
                row["result"] = f"would repoint to legal-docs/{new_key}"
            report.append(row)
            print(f"  {row['result'][:40]:42} {d['title'][:60]}", flush=True)

    counts = collections.Counter(r["result"].split(" to ")[0].split(":")[0] for r in report)
    print(json.dumps(counts, indent=1))
    for r in report:
        if r["result"].startswith("UNPROVEN"):
            print("  unproven:", r["title"][:70])
    (REPO / "scripts" / ".shared_storage_report.json").write_text(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
