#!/usr/bin/env python3
"""
Ingest the Judiciary of Zambia's court RULES and FEE SCHEDULES from the
official rules-resources archive.

WHY: Levy's users keep asking procedural and cost questions — filing during
Michaelmas vacation, how much a Notice of Appeal costs, which rules govern the
Small Claims Court — and the corpus was almost entirely statutes and judgments.
The Judiciary publishes this exact material at:

    /category/resources/rules-resources/

Three shapes live there, handled differently:

  * A post with an attached PDF (e.g. Small Claims Court Rules 2023):
    download, ingest, OCR if it is a scan. Reuses the judgment pipeline.
  * A post whose body IS the content — the fee schedules are inline HTML
    tables ("Notice of Appeal 150.00"). Ingest the extracted text.
  * A bare title page with neither (the "... Rules 2016" stubs the site never
    actually populated): skipped, because a title with no text is exactly the
    stub data we are trying to eliminate. Its URL is not lost — a real Rules
    document, when the site publishes one, will be picked up on a re-run.

Every ingested document gets canonical_url set to its official page, so a user
can always click through to the source even when we hold only extracted text.

SOURCE: judiciaryzambia.com only. Not ZambiaLII, not the Law Reports.

Usage:
  backend/.venv/bin/python scripts/ingest_court_rules_fees.py --dry-run
  backend/.venv/bin/python scripts/ingest_court_rules_fees.py
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import warnings
from html import unescape
from pathlib import Path

import httpx

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")

from app.db.supabase import get_db, insert_chunks       # noqa: E402
from app.services.embedder import get_embeddings          # noqa: E402
from harvest_judiciary_judgments import (                 # noqa: E402
    DOWNLOAD_DIR, pages_of, slug, upload,
)

BASE = "https://judiciaryzambia.com"
ARCHIVE = f"{BASE}/category/resources/rules-resources/"

# Pages in this archive that are navigation or institutional, not law.
SKIP = re.compile(
    r"(feed|wp-json|introduction|services|service-charters|court-operations|"
    r"women-in-the-judiciary|computerization|administration|contact|"
    r"the-child-justice-forum|^court-of-appeal-2$|^constitutional-court$|"
    r"^supreme-court$|^high-court$|^subordinate-courts?$|^local-courts?$|"
    r"^small-claims-court$)",
    re.I,
)

COURT_BY_KEYWORD = [
    ("supreme", "Supreme Court of Zambia"),
    ("constitutional", "Constitutional Court of Zambia"),
    ("court-of-appeal", "Court of Appeal of Zambia"),
    ("court of appeal", "Court of Appeal of Zambia"),
    ("high-court", "High Court of Zambia"),
    ("high court", "High Court of Zambia"),
    ("small-claims", "Small Claims Court of Zambia"),
    ("small claims", "Small Claims Court of Zambia"),
    ("subordinate", "Subordinate Court of Zambia"),
    ("local-court", "Local Courts of Zambia"),
    ("local court", "Local Courts of Zambia"),
]


def client() -> httpx.Client:
    return httpx.Client(timeout=40, follow_redirects=True, verify=False,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; LevyResearch/1.0; +https://levylegal.ai)"})


# The archive pages carry a "recent decisions" sidebar, so the listing bleeds
# in judgment posts (HPF 152, CCZ 0003, APP 146...). Those belong to the
# judgment corpus and must never be filed as a court rule. Reject anything that
# looks like a case citation or a "Party v Party" title.
JUDGMENT_SHAPE = re.compile(
    r"(\b(scz|app|appeal|caz|ccz|hp|hpf|hpa|hpc|sp)\b[-_ ]?\d"
    r"|\bv(s|ersus)?\b.+\b(19|20)\d\d\b"
    r"|\bcoram\b|\bjustice\b)",
    re.I,
)


def looks_like_judgment(url: str, title: str) -> bool:
    return bool(JUDGMENT_SHAPE.search(url) or JUDGMENT_SHAPE.search(title))


def court_of(text: str) -> str:
    low = text.lower()
    for kw, court in COURT_BY_KEYWORD:
        if kw in low:
            return court
    return "Judiciary of Zambia"


def kind_of(text: str) -> str:
    return "fee_schedule" if re.search(r"\bfee", text, re.I) else "court_rule"


def archive_posts(c: httpx.Client, delay: float) -> list[str]:
    r = c.get(ARCHIVE)
    pg = [int(n) for n in re.findall(r"/rules-resources/page/(\d+)/", r.text)]
    last = max(pg) if pg else 1
    posts: list[str] = []
    seen = set()
    for n in range(1, last + 1):
        u = ARCHIVE if n == 1 else f"{ARCHIVE}page/{n}/"
        rr = c.get(u)
        time.sleep(delay)
        for href in re.findall(r'href="(https://judiciaryzambia\.com/[a-z0-9\-]+/)"', rr.text):
            sl = href.rstrip("/").rsplit("/", 1)[-1]
            if href.rstrip("/").count("/") != 3 or SKIP.search(sl) or href in seen:
                continue
            seen.add(href)
            posts.append(href)
    return posts


def extract(c: httpx.Client, url: str) -> tuple[str | None, str]:
    """Return (pdf_url_or_None, article_text)."""
    r = c.get(url)
    pdfs = [p for p in re.findall(r'href="([^"]+\.pdf)"', r.text, re.I) if "/uploads/" in p]
    art = re.search(r"<article.*?</article>", r.text, re.S)
    body = art.group(0) if art else r.text
    body = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    text = unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))).strip()
    return (pdfs[0] if pdfs else None), text


def title_from(url: str) -> str:
    sl = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"\s+", " ", sl.replace("-", " ")).strip().title()


def already() -> set[str]:
    db = get_db()
    rows = (db.table("legal_documents").select("canonical_url")
            .in_("document_type", ["court_rule", "fee_schedule"]).execute().data) or []
    return {r["canonical_url"] for r in rows if r.get("canonical_url")}


def chunk_text(text: str, target: int = 1100) -> list[str]:
    # Split on paragraph and sentence breaks first; then HARD-slice any piece
    # that is still oversized. HTML-extracted text (the fee tables and the
    # Magistrates rules) often has no blank lines at all, so without the hard
    # slice a 22,000-char rulebook became one useless chunk that matched
    # nothing precisely — the opposite of what a citation-grounded corpus needs.
    cap = int(target * 1.4)
    rough = [p.strip() for p in re.split(r"\n\s*\n|(?<=[.;])\s{2,}", text) if p.strip()]
    pieces = []
    for p in rough:
        while len(p) > cap:
            cut = p.rfind(" ", target, cap)
            if cut == -1:
                cut = cap
            pieces.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            pieces.append(p)
    out, cur = [], ""
    for p in pieces:
        if len(cur) + len(p) + 2 <= cap:
            cur = (cur + "\n\n" + p).strip()
        else:
            if cur:
                out.append(cur)
            cur = p
    if cur:
        out.append(cur)
    return out or ([text] if text.strip() else [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()

    db = get_db()
    have = already()
    ingested = skipped = stubs = failed = 0

    with client() as c:
        posts = archive_posts(c, args.delay)
        print(f"{len(posts)} candidate rule/fee posts; {len(have)} already held\n")
        for url in posts:
            if url in have:
                skipped += 1
                continue
            pdf_url, text = extract(c, url)
            time.sleep(args.delay)
            title = title_from(url)
            if looks_like_judgment(url, title):
                skipped += 1
                continue
            kind = kind_of(title + " " + text[:200])
            court = court_of(title)

            # A page with no PDF and too little text is a title-only stub. Skip
            # it: an empty document is the exact thing we are removing, not
            # adding. Its URL stays discoverable for a future populated version.
            if not pdf_url and len(text) < 200:
                stubs += 1
                print(f"  stub (no content): {title[:50]}")
                continue

            if args.dry_run:
                how = "PDF" if pdf_url else f"text {len(text)}c"
                print(f"  would ingest [{kind}/{court.split()[0]}] {how}: {title[:48]}")
                ingested += 1
                continue

            try:
                if pdf_url:
                    r = c.get(pdf_url)
                    time.sleep(args.delay)
                    content = r.content
                    if not content.startswith(b"%PDF") or len(content) < 8000:
                        stubs += 1
                        continue
                    from app.services.form_ingester import ingest_form_pdf
                    key = slug(title) + ".pdf"
                    local = DOWNLOAD_DIR / key
                    local.write_bytes(content)
                    desc = f"{kind.replace('_',' ').title()} of the {court}. Published by the Judiciary of Zambia."
                    res = ingest_form_pdf(str(local), title=title,
                        short_name=title[:80], description=desc,
                        document_type=kind, category="procedure",
                        issuing_authority=court, source_url=url)
                    did = res["document"]["id"]
                    sp = upload(content, key)
                    db.table("legal_documents").update({
                        "is_global": True, "owner_id": None, "pdf_storage_path": sp,
                        "pdf_page_count": pages_of(content), "pdf_size_bytes": len(content),
                        "canonical_url": url, "document_type": kind,
                    }).eq("id", did).execute()
                    # OCR a scanned rules PDF inline so it is searchable, not just openable
                    if (res.get("chunks_created") or 0) <= 1:
                        from ocr_backfill_tesseract import promote_scanned
                        promote_scanned(did, title=title[:56])
                else:
                    # Inline content (the fee tables). Store the text directly.
                    header = (f"{title}\n\n{kind.replace('_',' ').title()} of the "
                              f"{court}, published by the Judiciary of Zambia.\n\n")
                    pieces = chunk_text(header + text)
                    embs = get_embeddings(pieces)
                    doc = db.table("legal_documents").insert({
                        "title": title, "short_name": title[:80],
                        "document_type": kind, "canonical_url": url, "source_url": url,
                        "is_global": True, "owner_id": None, "year": 2026,
                    }).execute().data[0]
                    did = doc["id"]
                    recs = [{"document_id": did, "content": t, "embedding": e,
                             "metadata": {"act_name": title, "document_type": kind,
                                          "category": "procedure", "issuing_authority": court,
                                          "source_url": url, "is_header": i == 0},
                             "chunk_index": i, "page_start": 1, "page_end": 1}
                            for i, (t, e) in enumerate(zip(pieces, embs))]
                    insert_chunks(recs)
                    db.table("legal_documents").update({"total_chunks": len(recs)}).eq("id", did).execute()
                ingested += 1
                print(f"  [{ingested}] {kind:12} {court.split()[0]:12} <- {title[:44]}")
            except Exception as e:  # noqa: BLE001
                print(f"  ! {title[:40]}: {str(e)[:70]}")
                failed += 1

    print(f"\nSUMMARY ingested={ingested} skipped={skipped} stubs={stubs} failed={failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
