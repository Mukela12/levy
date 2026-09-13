#!/usr/bin/env python3
"""Harvest the long tail of Zambian Acts from the National Assembly's own
Acts library (parliament.gov.zm/acts-of-parliament), the official publisher.

The listing has about 1,030 entries: the consolidated Chapters of the Laws of
Zambia (no Act number) and every Act passed since 1997 including amendments.
Levy held about 300. This walks the listing, skips what the corpus already
has (by title and by PDF hash), pulls each Act's PDF from its node page,
ingests it through the statute parser, and then writes the listing's own
title, number and year over the parser's guess, because parser titles are
junk ("(MISCELLANEOUS PROVISIONS) ACT" was how Cap 74 sat in the corpus).

Scanned PDFs (no text layer) are not ingested; they are written to
needs_ocr.txt for an OCR pass, so no stub ever enters the library.

  OPENAI_API_KEY=<harvest key> python scripts/harvest_parliament_acts.py [--limit N] [--dry-run] [--amendments]

Principal Acts first; amendment Acts only with --amendments. Resumable: the
cache remembers every node already handled.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "scripts"))
import _dns_resilient  # noqa: F401
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")

from app.db.supabase import get_db  # noqa: E402
from app.services.ingester import ingest_pdf  # noqa: E402
from harvest_judgments_v2 import store, pages_of  # noqa: E402

BASE = "https://www.parliament.gov.zm"
CACHE = REPO / "scripts" / ".parliament_cache.json"
NEEDS_OCR = REPO / "scripts" / "needs_ocr.txt"
WORK = Path.home() / "levy-test-fixtures" / "parliament-acts"
UA = {"User-Agent": "Mozilla/5.0 LevyHarvest/1.0"}
ROW = re.compile(r'<a href="(/node/\d+)">([^<]+?)\s*<div class=\'act-number-appended\'>\(\s*([^)]*)\)</div></a>')
PDF = re.compile(r'href="(https://www\.parliament\.gov\.zm/sites/default/files/documents/acts/[^"]+\.pdf)"')
MAX_PAGES = 450


def http() -> httpx.Client:
    return httpx.Client(timeout=90.0, follow_redirects=True, verify=False, headers=UA)


def crawl_index(c: httpx.Client) -> list[dict]:
    rows, page = [], 0
    while True:
        for attempt in range(3):
            try:
                r = c.get(f"{BASE}/acts-of-parliament", params={"page": page})
                break
            except Exception:  # noqa: BLE001
                time.sleep(3)
        else:
            break
        found = ROW.findall(r.text)
        if not found:
            break
        for node, title, no in found:
            rows.append({"node": node, "title": html.unescape(title).strip(), "no": html.unescape(no).strip()})
        page += 1
        time.sleep(0.3)
    return rows


def norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\(?\b(?:act\s*)?no\.?\s*\d+\s*of\s*\d{4}\)?", " ", s)
    s = re.sub(r"\bcap\.?\s*\d+\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\b(the|act|of|and|zambia|republic)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def held_keys(db) -> set[str]:
    out, i = set(), 0
    while True:
        rows = (db.table("legal_documents").select("title,short_name,document_type")
                .in_("document_type", ["act", "bill", "court_rule"]).range(i, i + 999).execute().data or [])
        for r in rows:
            if r["document_type"] == "bill":
                continue
            for k in ("title", "short_name"):
                if r.get(k):
                    out.add(norm(r[k]))
        if len(rows) < 1000:
            break
        i += 1000
    return out


def parse_entry(e: dict) -> dict:
    title = re.sub(r"\s+", " ", e["title"]).strip(" .")
    if not title.lower().startswith("the "):
        title = "The " + title
    m = re.search(r"No\.?\s*(\d+)\s*of\s*(\d{4})", e["no"])
    act_no = f"No. {m.group(1)} of {m.group(2)}" if m else ""
    ym = re.search(r"(19|20)\d\d", e["no"]) or re.search(r"(?:,\s*|\()((?:19|20)\d\d)\)?\s*$", title)
    year = int(ym.group(0) if ym and ym.re.pattern.startswith("(19") else (ym.group(1) if ym else 0)) or None
    short = title[4:] + (f" ({act_no})" if act_no else "")
    amendment = "amendment" in title.lower()
    return {**e, "title": title, "act_number": act_no, "year": year, "short": short, "amendment": amendment}


def pdf_link(c: httpx.Client, node: str) -> str | None:
    for attempt in range(3):
        try:
            r = c.get(BASE + node)
            m = PDF.search(r.text)
            return m.group(1) if m else None
        except Exception:  # noqa: BLE001
            time.sleep(3)
    return None


def text_chars(pdf: bytes, pages: int = 3) -> int:
    try:
        from pypdf import PdfReader
        import io
        rd = PdfReader(io.BytesIO(pdf))
        return sum(len((rd.pages[i].extract_text() or "").strip()) for i in range(min(pages, len(rd.pages))))
    except Exception:  # noqa: BLE001
        return 0


def patch_chunks(db, doc_id: str, title: str, short: str) -> int:
    n, i = 0, 0
    while True:
        rows = db.table("legal_chunks").select("id,metadata").eq("document_id", doc_id).range(i, i + 999).execute().data or []
        for r in rows:
            m = dict(r.get("metadata") or {})
            m["act_name"], m["act_title"] = short, title
            db.table("legal_chunks").update({"metadata": m}).eq("id", r["id"]).execute()
            n += 1
        if len(rows) < 1000:
            break
        i += 1000
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--amendments", action="store_true", help="also harvest amendment Acts")
    ap.add_argument("--index", default="", help="reuse a saved index.json instead of crawling")
    ap.add_argument("--shard", default="1/1", help="k/n: handle the nodes whose id hashes to shard k of n (run n processes)")
    args = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    k, n = (int(x) for x in args.shard.split("/"))
    cache_path = CACHE if n == 1 else CACHE.with_suffix(f".{k}of{n}.json")
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    if n > 1 and CACHE.exists():
        # a single-process run's progress counts for every shard
        cache = {**json.loads(CACHE.read_text()), **cache}
    # Shards partition on the node id, not on list position, so concurrently
    # running shards never overlap even when their held-sets differ.
    def mine(e: dict) -> bool:
        return n == 1 or (int(e["node"].rsplit("/", 1)[-1]) % n) == (k - 1)
    db = get_db()
    c = http()

    if args.index and Path(args.index).exists():
        index = json.loads(Path(args.index).read_text())
    else:
        print("crawling the Acts listing ...", flush=True)
        index = crawl_index(c)
    entries = [parse_entry(e) for e in index]
    held = held_keys(db)
    todo = [e for e in entries if e["node"] not in cache and norm(e["title"]) not in held
            and (args.amendments or not e["amendment"]) and mine(e)]
    todo.sort(key=lambda e: (e["amendment"], -(e["year"] or 0)))
    print(f"index={len(entries)} held={len(held)} cached={len(cache)} to do={len(todo)}"
          f" (principal={sum(1 for e in todo if not e['amendment'])}, amendment={sum(1 for e in todo if e['amendment'])})", flush=True)
    if args.limit:
        todo = todo[: args.limit]

    done = skipped = failed = scanned = 0
    for i, e in enumerate(todo, 1):
        tag = f"[{i}/{len(todo)}] {e['title'][:60]}"
        if args.dry_run:
            print(f"  would harvest {tag} {e['act_number']}"); continue
        try:
            url = pdf_link(c, e["node"])
            if not url:
                cache[e["node"]] = {"status": "no_pdf_link", "title": e["title"]}
                print(f"  no PDF link {tag}", flush=True); failed += 1; continue
            r = c.get(url)
            body = r.content
            if r.status_code != 200 or not body[:5].startswith(b"%PDF"):
                cache[e["node"]] = {"status": f"bad_download_{r.status_code}", "title": e["title"], "url": url}
                print(f"  bad download {tag} ({r.status_code})", flush=True); failed += 1; continue
            h = hashlib.sha256(body).hexdigest()
            if db.table("legal_documents").select("id").eq("pdf_hash", h).limit(1).execute().data:
                cache[e["node"]] = {"status": "hash_held", "title": e["title"]}
                print(f"  hash held {tag}", flush=True); skipped += 1; continue
            npages = pages_of(body)
            if npages > MAX_PAGES:
                cache[e["node"]] = {"status": "too_long", "pages": npages, "title": e["title"], "url": url}
                print(f"  too long {tag} ({npages} pages)", flush=True); skipped += 1; continue
            if text_chars(body) < 200:
                cache[e["node"]] = {"status": "needs_ocr", "title": e["title"], "url": url, "pages": npages}
                with NEEDS_OCR.open("a") as f:
                    f.write(f"{e['node']}|{e['title']}|{url}|{npages}\n")
                print(f"  scanned, queued for OCR {tag} ({npages} pages)", flush=True); scanned += 1; continue
            local = WORK / (re.sub(r"[^A-Za-z0-9]+", "_", e["title"]).strip("_")[:80] + ".pdf")
            local.write_bytes(body)
            res = ingest_pdf(str(local), overrides={
                "title": e["title"], "short_name": e["short"], "act_number": e["act_number"], "year": e["year"]})
            if res.get("status") == "skipped":
                cache[e["node"]] = {"status": "hash_held", "title": e["title"]}
                skipped += 1; continue
            doc = res["document"]
            sp = store(body, local.name)
            db.table("legal_documents").update({
                "title": e["title"], "short_name": e["short"], "act_number": e["act_number"], "year": e["year"],
                "is_global": True, "owner_id": None, "pdf_storage_path": sp, "pdf_page_count": npages,
                "pdf_size_bytes": len(body), "canonical_url": url, "source_url": url,
            }).eq("id", doc["id"]).execute()
            nch = res.get("chunks_created") or doc.get("total_chunks") or 0
            cache[e["node"]] = {"status": "ingested", "title": e["title"], "doc_id": doc["id"], "chunks": nch}
            print(f"  INGESTED {tag} {e['act_number']} pages={npages} chunks={nch}", flush=True)
            done += 1
        except Exception as ex:  # noqa: BLE001
            cache[e["node"]] = {"status": f"error: {type(ex).__name__}", "title": e["title"]}
            print(f"  FAILED {tag}: {type(ex).__name__}: {str(ex)[:120]}", flush=True); failed += 1
        finally:
            cache_path.write_text(json.dumps(cache, indent=0))
            time.sleep(0.4)
    print(f"\nDONE ingested={done} skipped={skipped} scanned={scanned} failed={failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
