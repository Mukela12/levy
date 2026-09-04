#!/usr/bin/env python3
"""
Full-corpus integrity sweep. Guarantees the two properties Levy's accuracy
depends on: every citation resolves to something a user can open, and every
judgment is labelled with the court that actually decided it.

Why paginated: PostgREST caps a plain .execute() at 1000 rows, so earlier
one-shot sweeps silently audited only the first 1000 of ~1400 documents. This
pages through everything.

What it does (idempotent; safe to re-run):
  1. LABELS  — re-derive each judgment's court from its own opening text
     ("IN THE SUPREME COURT ...") and correct any mismatch. The title and the
     archive it was filed under are NOT trusted: an appeal judgment names other
     courts, and archives mix courts. Specialised High Court divisions
     (Family / Commercial / Bail / Economic Crimes) are preserved.
  2. ORPHANS — a judgment with OCR text but no openable target (PDF upload
     failed) is re-linked: first from its own source_url, else by locating its
     page on judiciaryzambia.com. Text is never thrown away when it can be linked.
  3. DEAD-ENDS — a row with no PDF, no text, and no link is unusable and is
     removed. It re-ingests cleanly on the next harvest.

--dry-run reports what it would do and changes nothing.

Source for re-linking is judiciaryzambia.com only. Never ZambiaLII.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import warnings
from pathlib import Path

import httpx

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")
from app.db.supabase import get_db  # noqa: E402

HDR = re.compile(
    r"IN\s+THE\s+(SUPREME\s+COURT|COURT\s+OF\s+APPEAL|CONSTITUTIONAL\s+COURT|"
    r"HIGH\s+COURT|SUBORDINATE\s+COURT)", re.I)
FULL = {"SUPREME COURT": "Supreme Court of Zambia",
        "COURT OF APPEAL": "Court of Appeal of Zambia",
        "CONSTITUTIONAL COURT": "Constitutional Court of Zambia",
        "HIGH COURT": "High Court of Zambia",
        "SUBORDINATE COURT": "Subordinate Court of Zambia"}
SPECIALISED = ("Division", "Bail", "Crimes")  # keep these High Court sub-labels


def all_documents(db) -> list[dict]:
    out, step, off = [], 1000, 0
    while True:
        page = (db.table("legal_documents")
                .select("id,title,document_type,pdf_storage_path,canonical_url,source_url,total_chunks")
                .range(off, off + step - 1).execute().data) or []
        out += page
        if len(page) < step:
            return out
        off += step


def client() -> httpx.Client:
    return httpx.Client(timeout=20, follow_redirects=True, verify=False,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; LevyResearch/1.0)"})


def find_page(c: httpx.Client, title: str) -> str | None:
    words = re.sub(r"^(APP|Appeal|CAZ|CCZ|SCZ|SP|\d{4}HP\w*|\d+)[\s.]*", "", title, flags=re.I).split()
    if not words:
        return None
    key = "+".join(words[:3])
    w1 = words[0].lower().strip(".,")
    try:
        r = c.get(f"https://judiciaryzambia.com/?s={key}")
    except Exception:
        return None
    posts = [p for p in sorted(set(re.findall(
        r'href="(https://judiciaryzambia\.com/[a-z0-9\-]+/)"', r.text)))
        if w1 and w1 in p.lower()
        and not re.search(r'/category/|/tag/|/page/|/author/|contact|administration', p)]
    return posts[0] if posts else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    db = get_db()
    docs = all_documents(db)
    judg = [d for d in docs if d.get("document_type") == "judgment"]
    print(f"corpus: {len(docs)} documents, {len(judg)} judgments"
          + ("  [DRY RUN]" if args.dry_run else ""), flush=True)

    labels_fixed = relinked = removed = 0

    # 1) LABELS
    for d in judg:
        ch = (db.table("legal_chunks").select("id,metadata,content")
              .eq("document_id", d["id"]).order("chunk_index").limit(3).execute().data) or []
        if not ch:
            continue
        auth = (ch[0].get("metadata") or {}).get("issuing_authority") or ""
        if any(s in auth for s in SPECIALISED):
            continue
        m = HDR.search(" ".join((c.get("content") or "")[:500] for c in ch)[:800])
        if not m:
            continue
        right = FULL[re.sub(r"\s+", " ", m.group(1).upper())]
        if right != auth:
            if args.dry_run:
                print(f"  label: {(d.get('title') or '')[:44]}  {auth!r} -> {right}")
            else:
                allch = (db.table("legal_chunks").select("id,metadata")
                         .eq("document_id", d["id"]).execute().data) or []
                for c in allch:
                    md = c.get("metadata") or {}
                    md["issuing_authority"] = right
                    db.table("legal_chunks").update({"metadata": md}).eq("id", c["id"]).execute()
            labels_fixed += 1

    # 2) ORPHANS then 3) DEAD-ENDS (re-fetch state; labels pass did not touch these fields)
    docs = all_documents(db)
    judg = [d for d in docs if d.get("document_type") == "judgment"]
    with client() as c:
        for d in judg:
            openable = d.get("pdf_storage_path") or d.get("canonical_url") or d.get("source_url")
            has_text = (d.get("total_chunks") or 0) > 1
            if openable:
                continue
            if has_text:  # orphan: keep the text, find a link
                link = d.get("source_url") or find_page(c, d.get("title") or "")
                if link:
                    if args.dry_run:
                        print(f"  relink: {(d.get('title') or '')[:44]} -> {link.split('/')[-2][:34]}")
                    else:
                        db.table("legal_documents").update({"canonical_url": link}).eq("id", d["id"]).execute()
                    relinked += 1
                    time.sleep(0.6)
                else:
                    print(f"  ORPHAN, no page found (kept, no link): {(d.get('title') or '')[:44]}")
            else:  # dead-end: no pdf, no text, no link
                if args.dry_run:
                    print(f"  remove dead-end: {(d.get('title') or '')[:50]}")
                else:
                    db.table("legal_chunks").delete().eq("document_id", d["id"]).execute()
                    db.table("legal_documents").delete().eq("id", d["id"]).execute()
                removed += 1

    # FINAL REPORT
    docs = all_documents(db)
    judg = [d for d in docs if d.get("document_type") == "judgment"]
    unopenable = [d for d in judg if not (d.get("pdf_storage_path") or d.get("canonical_url") or d.get("source_url"))]
    import collections
    courts = collections.Counter()
    for d in judg:
        ch = (db.table("legal_chunks").select("metadata").eq("document_id", d["id"])
              .order("chunk_index").limit(1).execute().data) or []
        courts[(ch[0].get("metadata") if ch else {}).get("issuing_authority") or "unlabelled"] += 1
    print(f"\n{'DRY RUN — ' if args.dry_run else ''}SWEEP COMPLETE")
    print(f"  labels corrected : {labels_fixed}")
    print(f"  orphans re-linked: {relinked}")
    print(f"  dead-ends removed: {removed}")
    print(f"  documents now    : {len(docs)}  |  judgments: {len(judg)}")
    print(f"  UNOPENABLE judgments remaining: {len(unopenable)}")
    print("  court distribution:")
    for k, v in courts.most_common():
        print(f"    {k:40} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
