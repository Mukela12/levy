#!/usr/bin/env python3
"""
Bulk-harvest Zambian judgments from judiciaryzambia.com — the Judiciary of
Zambia's OWN site, whose robots.txt only disallows /wp-admin/ (content is
fully crawlable). This is the clean, no-account path to a precedent corpus
(Laws.Africa's API serves legislation not judgments; ZambiaLII forbids
scraping). The Judiciary publishes each judgment as a WordPress post with
the PDF attached under /wp-content/uploads/.

Strategy:
  1. Pull every post URL from the WordPress sitemaps.
  2. Skip obvious non-judgment posts (judge bios, events, news, cause
     lists, pages).
  3. Fetch each candidate post, extract the attached judgment PDF link.
  4. Download + ingest as document_type='judgment' (idempotent by hash),
     deriving the case title + citation from the filename.
  5. Upload PDF to storage + mark is_global so it's citable + downloadable.

Politeness: small delay between requests; capped at --limit ingested.

Usage:
  /Users/mukelakatungu/levy/.claude/worktrees/lucid-bartik-c2ad7f/.venv/bin/python \
      scripts/harvest_judiciary_judgments.py --limit 150 --scan 1200
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import time
import urllib.parse
import uuid
import warnings
from pathlib import Path

import httpx

warnings.filterwarnings("ignore", message="Unverified HTTPS request")
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")

from app.db.supabase import get_db  # noqa: E402
from app.services.form_ingester import ingest_form_pdf  # noqa: E402

BASE = "https://judiciaryzambia.com"
BUCKET = "legal-docs"
DOWNLOAD_DIR = Path("/Users/mukelakatungu/levy-test-fixtures/judiciary-judgments")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

SITEMAPS = [
    f"{BASE}/wp-sitemap-posts-post-1.xml",
    f"{BASE}/wp-sitemap-posts-post-2.xml",
    f"{BASE}/wp-sitemap-posts-post-3.xml",
]

# URL slugs that are clearly NOT judgments.
SKIP_SLUG = re.compile(
    r"/(hon-|justice-|judge|the-clerk|registrar|about|contact|news|event|"
    r"cause-?list|vacanc|tender|procurement|speech|press|gallery|charter|"
    r"strategic|annual-report|practice-direction|holiday|notice)",
    re.I,
)
# Judgment-ish signals in a PDF URL.
JUDGMENT_PDF = re.compile(r"(app[-_]?\d|scz|caz|ccz|-vs-|-v-|coram|judgment|appeal)", re.I)


def http() -> httpx.Client:
    return httpx.Client(timeout=45, follow_redirects=True, verify=False,
                        headers={"User-Agent": "Mozilla/5.0 LevyIngest/1.0"})


def sitemap_post_urls(client: httpx.Client) -> list[str]:
    urls: list[str] = []
    for sm in SITEMAPS:
        try:
            r = client.get(sm)
            if r.status_code != 200:
                continue
            for loc in re.findall(r"<loc>(.*?)</loc>", r.text):
                loc = loc.strip()
                if loc.startswith(BASE) and loc.endswith("/") and not SKIP_SLUG.search(loc):
                    urls.append(loc)
        except Exception:
            continue
    # de-dupe, keep order
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u); out.append(u)
    return out


def find_judgment_pdf(client: httpx.Client, page_url: str) -> str | None:
    try:
        r = client.get(page_url)
        if r.status_code != 200:
            return None
    except Exception:
        return None
    pdfs = re.findall(r'href=["\']([^"\']+\.pdf)["\']', r.text, re.I)
    # prefer judgment-looking PDFs hosted on the judiciary/zambialii media
    cands = [p for p in pdfs if "/uploads/" in p or "media.zambialii" in p or "judiciaryzambia" in p]
    cands = cands or pdfs
    for p in cands:
        if JUDGMENT_PDF.search(p):
            return urllib.parse.urljoin(page_url, p)
    return urllib.parse.urljoin(page_url, cands[0]) if cands else None


def derive(url: str, content: bytes) -> tuple[str, str | None]:
    fname = urllib.parse.unquote(url.rsplit("/", 1)[-1].rsplit(".", 1)[0])
    m = re.search(r"(APP|SCZ|CAZ|CCZ)[-_ ]?(\d+)[-_ ]?(\d{4})", fname, re.I)
    citation = f"{m.group(1).upper()} No. {m.group(2)} of {m.group(3)}" if m else None
    raw = re.sub(r"(APP|SCZ|CAZ|CCZ)[-_ ]?\d+[-_ ]?\d{4}", "", fname, flags=re.I)
    raw = re.split(r"[-_ ]?Coram", raw, flags=re.I)[0]
    name = re.sub(r"[-_]+", " ", raw).strip()
    name = re.sub(r"\bvs\b", "v", name, flags=re.I).strip(" -–")
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = fname
    title = (name if not citation else f"{name} ({citation})")[:160]
    return title, citation


def slug(s: str) -> str:
    return (re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_") or uuid.uuid4().hex)[:80]


def upload(content: bytes, key: str) -> str:
    db = get_db()
    try:
        db.storage.from_(BUCKET).upload(path=key, file=content,
            file_options={"content-type": "application/pdf", "upsert": "true"})
    except Exception as e:  # noqa: BLE001
        if "exists" in str(e).lower() or "duplicate" in str(e).lower():
            try: db.storage.from_(BUCKET).remove([key])
            except Exception: pass
            db.storage.from_(BUCKET).upload(path=key, file=content,
                file_options={"content-type": "application/pdf"})
        else:
            raise
    return f"{BUCKET}/{key}"


def pages_of(content: bytes) -> int:
    try:
        from pypdf import PdfReader
        return len(PdfReader(io.BytesIO(content)).pages)
    except Exception:
        return 0


# crude area inference from the title/citation keywords
AREA_HINTS = [
    ("employment", r"dismiss|employ|labour|redundan|terminal benefit|industrial"),
    ("land", r"land|title|lease|tenanc|trespass|estate of|caveat|plot"),
    ("family", r"matrimon|divorce|custody|maintenance|marriage"),
    ("succession", r"administrat|intestate|will|testate|deceased estate"),
    ("criminal", r"the people|murder|theft|fraud|rape|defile|conviction|sentence"),
    ("company", r"compan|director|winding|insolven|shareholder|liquidat"),
    ("tax", r"revenue authority|\btax\b|customs|vat|tariff"),
    ("constitutional", r"attorney general|constitution|electoral|judicial review|bill of rights"),
    ("tort", r"negligen|defamat|damages|personal injury|nuisance"),
    ("commercial", r"bank|guarantee|loan|contract|sale of goods|insurance"),
]


def infer_area(title: str) -> str:
    low = title.lower()
    for area, pat in AREA_HINTS:
        if re.search(pat, low):
            return area
    return "general"


def already_ingested_urls() -> set[str]:
    rows = (get_db().table("legal_documents").select("canonical_url")
            .eq("document_type", "judgment").execute()).data or []
    return {r["canonical_url"] for r in rows if r.get("canonical_url")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=120, help="max judgments to ingest")
    ap.add_argument("--scan", type=int, default=1500, help="max post pages to scan")
    args = ap.parse_args()

    have = already_ingested_urls()
    print(f"Already have {len(have)} judgments by URL.")
    ingested = scanned = skipped = failed = 0
    seen_pdf: set[str] = set()

    with http() as client:
        urls = sitemap_post_urls(client)
        print(f"Collected {len(urls)} candidate post URLs from sitemaps.")
        for page_url in urls:
            if ingested >= args.limit or scanned >= args.scan:
                break
            scanned += 1
            pdf_url = find_judgment_pdf(client, page_url)
            if not pdf_url or pdf_url in seen_pdf:
                continue
            seen_pdf.add(pdf_url)
            if pdf_url in have:
                skipped += 1
                continue
            try:
                r = client.get(pdf_url)
            except Exception:
                failed += 1; continue
            content = r.content
            if r.status_code != 200 or not content.startswith(b"%PDF") or len(content) < 20_000:
                continue
            title, citation = derive(pdf_url, content)
            area = infer_area(title)
            key = slug(title) + ".pdf"
            local = DOWNLOAD_DIR / key
            local.write_bytes(content)
            desc = (f"Zambian court judgment ({area} law)."
                    + (f" Citation: {citation}." if citation else "")
                    + " Published by the Judiciary of Zambia.")
            try:
                res = ingest_form_pdf(str(local), title=title,
                    short_name=(citation or title)[:80], description=desc,
                    document_type="judgment", category=area,
                    issuing_authority="Judiciary of Zambia", source_url=pdf_url)
            except Exception as e:  # noqa: BLE001
                print(f"  ! ingest error: {e}"); failed += 1; continue
            if res["status"] == "skipped":
                skipped += 1; continue
            try:
                sp = upload(content, key)
                get_db().table("legal_documents").update({
                    "is_global": True, "owner_id": None, "pdf_storage_path": sp,
                    "pdf_page_count": pages_of(content), "pdf_size_bytes": len(content),
                    "canonical_url": pdf_url, "document_type": "judgment",
                }).eq("id", res["document"]["id"]).execute()
            except Exception as e:  # noqa: BLE001
                print(f"  ! storage error: {e}"); failed += 1; continue
            ingested += 1
            print(f"  [{ingested}/{args.limit}] ({area}) {title[:64]}")
            time.sleep(0.4)

    print(f"\nSUMMARY scanned={scanned} ingested={ingested} skipped={skipped} failed={failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
