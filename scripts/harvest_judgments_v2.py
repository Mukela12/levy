#!/usr/bin/env python3
"""Harvest RECENT Zambian judgments from judiciaryzambia.com (improved).

Why v2: the original harvester only followed direct `.pdf` hrefs, but the
Judiciary serves judgments through a "Delightful Downloads" endpoint
(`/?delightful-downloads=<id>` -> 302 -> /wp-content/uploads/...pdf). Recon
showed OLDER (2018) judgment PDFs are mostly 404 (purged), while RECENT
(2023-2025) judgments resolve ~100%. So v2:
  - follows the delightful-downloads redirect to get the PDF,
  - targets recent judgments (where files are live + precedent is current),
  - parses rich metadata (court, case number, parties, year, area) from the
    post slug so precedent search can filter.

Sources ONLY judiciaryzambia.com (the court's own public-domain judgments,
robots-open). Never zambialii.org. Never the copyrighted Zambia Law Reports.

Usage:
  .../python scripts/harvest_judgments_v2.py --limit 30 --since-year 2023
"""
from __future__ import annotations
import argparse, io, re, sys, time, urllib.parse, warnings
from pathlib import Path
import httpx

warnings.filterwarnings("ignore")
try:
    import urllib3; urllib3.disable_warnings()
except Exception:
    pass

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")
from app.db.supabase import get_db                         # noqa: E402
from app.services.form_ingester import ingest_form_pdf     # noqa: E402

BASE = "https://judiciaryzambia.com"
BUCKET = "legal-docs"
DL = Path("/tmp/levy-judgments"); DL.mkdir(parents=True, exist_ok=True)
SITEMAPS = [f"{BASE}/wp-sitemap-posts-post-{i}.xml" for i in (1, 2, 3)]

SKIP = re.compile(r"/(hon-|justice-|judge|registrar|about|contact|news|event|"
                  r"cause-?list|vacanc|tender|speech|press|gallery|charter|strategic|"
                  r"annual-report|practice-direction|holiday|notice|illegal-use)", re.I)
JUD = re.compile(r"(app-?no|appeal-no|comp-no|selected-jud|-vs-|-v-|ccz|scz|caz|"
                 r"the-people|\bhp[a-z]?[-]?\d|irc)", re.I)

# Court inference from case-number / slug tokens.
COURT_MAP = [
    (r"\bccz\b|constitutional", "Constitutional Court"),
    (r"\bscz\b|supreme", "Supreme Court"),
    (r"\bcaz\b|court-of-appeal", "Court of Appeal"),
    (r"\birc|comp-no-irc", "High Court (Industrial Relations Division)"),
    (r"\bhpc\b", "High Court (Commercial Division)"),
    (r"\bhpf\b|hpf-|\bhpfd?\b", "High Court (Family Division)"),
    (r"\bhpef\b|hpef-", "High Court (Economic & Financial Crimes)"),
    (r"\bhpa\b|hpa-|hpba", "High Court (Appellate / Bail)"),
    (r"\bhp[-]?\d|\bh-\d|hpef|hpr", "High Court"),
]
AREA_HINTS = [
    ("employment", r"dismiss|employ|labour|redundan|industrial|irc|pension|napsa|access-bank"),
    ("succession", r"administrat|intestate|estate|deceased|administratrix|administrator"),
    ("criminal", r"the-people|murder|theft|fraud|rape|defile|prosecut|director-f-public"),
    ("family", r"matrimon|divorce|custody|maintenance|marriage"),
    ("land", r"land|title|lease|tenanc|trespass|caveat|plot|property"),
    ("company", r"compan|director|winding|insolven|shareholder|limited-vs|trust-limited"),
    ("constitutional", r"attorney-general|constitution|electoral|judicial-review|anti-corruption"),
    ("commercial", r"bank|guarantee|loan|contract|transport|investment|trade"),
]
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()


def http():
    return httpx.Client(timeout=45, follow_redirects=True, verify=False,
                        headers={"User-Agent": "Mozilla/5.0 LevyIngest/1.0"})


def post_urls(c):
    out, seen = [], set()
    for sm in SITEMAPS:
        try:
            r = c.get(sm)
            if r.status_code != 200:
                continue
            for loc in re.findall(r"<loc>(.*?)</loc>", r.text):
                loc = loc.strip()
                if loc.startswith(BASE) and loc.endswith("/") and not SKIP.search(loc) and JUD.search(loc):
                    if loc not in seen:
                        seen.add(loc); out.append(loc)
        except Exception:
            continue
    return out


def fetch_pdf(c, post_url):
    """Return (pdf_bytes, pdf_url) or None. Handles delightful-downloads + direct."""
    try:
        html = c.get(post_url).text
    except Exception:
        return None
    # Prefer the delightful-downloads endpoint (how recent judgments are served).
    for cand in re.findall(r'(https://judiciaryzambia\.com/\?delightful-downloads=\d+)', html):
        try:
            r = c.get(cand)
            if r.status_code == 200 and r.content[:4] == b"%PDF" and len(r.content) > 15_000:
                return r.content, str(r.url)
        except Exception:
            pass
    for href in re.findall(r'href=["\']([^"\']+\.pdf)["\']', html, re.I):
        u = urllib.parse.urljoin(post_url, href)
        try:
            r = c.get(u)
            if r.status_code == 200 and r.content[:4] == b"%PDF" and len(r.content) > 15_000:
                return r.content, u
        except Exception:
            pass
    return None


def parse_slug(post_url):
    slug = post_url.rstrip("/").rsplit("/", 1)[-1]
    s = slug.lower()
    # year
    ys = re.findall(r"(20\d{2})", s)
    year = None
    for y in ys:
        if 2000 <= int(y) <= 2026:
            year = int(y); break
    # court
    court = "High Court"
    for pat, name in COURT_MAP:
        if re.search(pat, s):
            court = name; break
    # case number: grab a token group like 2025-hp-0252 / comp-no-irclk-442-2022 / hpa-011-2025
    cn = re.search(r"(comp-no-[a-z]+-\d+-\d{4}|20\d{2}-h[a-z]*-?\d+|hp[a-z]?-?\d+-?\d*|app-?no-\d+-\d{4}|appeal-no-\d+-\d{4}|(?:ccz|scz|caz)-?\d+-?\d*)", s)
    case_no = cn.group(1).replace("-", " ").upper().replace("NO ", "No. ") if cn else None
    # parties: between the leading case-number tokens and the trailing date/judge
    parties = s
    parties = re.sub(r"^(20\d{2}|comp|app|appeal|selected|hp[a-z]?|h|ccz|scz|caz|no|of|d|\d+|[a-z]{1,4})(-|$)", "", parties)
    m = re.search(r"([a-z].*?-(?:vs?|v)-.*?)(?:-(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b|-coram|-justice|-j$|$)", s)
    if m:
        parties = m.group(1)
    parties = re.sub(r"\b(vs)\b", "v", parties)
    parties = re.sub(r"[-_]+", " ", parties).strip().title()
    parties = re.sub(r"\bV\b", "v", parties)
    # area
    area = "general"
    for a, pat in AREA_HINTS:
        if re.search(pat, s):
            area = a; break
    title = parties or slug.replace("-", " ").title()
    if case_no:
        title = f"{title} ({case_no})"
    return {"title": title[:170], "case_no": case_no, "court": court,
            "year": year, "area": area, "parties": parties}


def pages_of(b):
    try:
        from pypdf import PdfReader
        return len(PdfReader(io.BytesIO(b)).pages)
    except Exception:
        return 0


def store(content, key):
    db = get_db()
    try:
        db.storage.from_(BUCKET).upload(path=key, file=content,
            file_options={"content-type": "application/pdf", "upsert": "true"})
    except Exception as e:
        if "exists" in str(e).lower() or "duplicate" in str(e).lower():
            try: db.storage.from_(BUCKET).remove([key])
            except Exception: pass
            db.storage.from_(BUCKET).upload(path=key, file=content,
                file_options={"content-type": "application/pdf"})
        else:
            raise
    return f"{BUCKET}/{key}"


def have_urls():
    rows = (get_db().table("legal_documents").select("canonical_url")
            .eq("document_type", "judgment").execute()).data or []
    return {r["canonical_url"] for r in rows if r.get("canonical_url")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--scan", type=int, default=400)
    ap.add_argument("--since-year", type=int, default=2023)
    args = ap.parse_args()

    have = have_urls()
    print(f"have {len(have)} judgments already")
    ingested = scanned = skipped = failed = 0
    with http() as c:
        urls = post_urls(c)
        # recent first: WP sitemaps are oldest->newest, so reverse.
        urls = list(reversed(urls))
        print(f"{len(urls)} judgment-looking posts; harvesting recent (>= {args.since_year})")
        for p in urls:
            if ingested >= args.limit or scanned >= args.scan:
                break
            meta = parse_slug(p)
            if meta["year"] and meta["year"] < args.since_year:
                continue
            scanned += 1
            got = fetch_pdf(c, p)
            if not got:
                failed += 1; continue
            content, pdf_url = got
            if pdf_url in have:
                skipped += 1; continue
            key = (re.sub(r"[^A-Za-z0-9._-]+", "_", meta["title"]).strip("_")[:80] or "judgment") + ".pdf"
            local = DL / key
            local.write_bytes(content)
            desc = (f"Zambian court judgment ({meta['area']} law), {meta['court']}."
                    + (f" Case {meta['case_no']}." if meta['case_no'] else "")
                    + (f" {meta['year']}." if meta['year'] else "")
                    + " Published by the Judiciary of Zambia.")
            try:
                res = ingest_form_pdf(str(local), title=meta["title"],
                    short_name=(meta["case_no"] or meta["title"])[:80], description=desc,
                    document_type="judgment", category=meta["area"],
                    issuing_authority=meta["court"], source_url=pdf_url)
            except Exception as e:
                print("  ! ingest:", e); failed += 1; continue
            if res["status"] == "skipped":
                skipped += 1; continue
            try:
                sp = store(content, key)
                patch = {"is_global": True, "owner_id": None, "pdf_storage_path": sp,
                         "pdf_page_count": pages_of(content), "pdf_size_bytes": len(content),
                         "canonical_url": pdf_url, "document_type": "judgment"}
                if meta["year"]:
                    patch["year"] = meta["year"]
                get_db().table("legal_documents").update(patch).eq("id", res["document"]["id"]).execute()
            except Exception as e:
                print("  ! store:", e); failed += 1; continue
            ingested += 1
            print(f"  [{ingested}/{args.limit}] ({meta['area']:>12} | {meta['court'][:22]:22}) {meta['title'][:55]}")
            time.sleep(0.5)
    print(f"\nSUMMARY scanned={scanned} ingested={ingested} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    sys.exit(main())
