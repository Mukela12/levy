#!/usr/bin/env python3
"""
Harvest Zambian judgments from the Judiciary of Zambia's OWN decision
listings, court by court.

WHY THIS EXISTS, given harvest_judiciary_judgments.py already harvests the
same site: that script discovers posts from three WordPress post sitemaps
(`wp-sitemap-posts-post-{1,2,3}.xml`). Those do not cover the decisions
archive, so it found 146 judgments and, critically, ZERO from the Supreme
Court. In a precedent system the Supreme Court is the apex binding
authority, so Levy could not cite a single binding case from its own corpus.

The decisions ARE published, in per-court category archives:

    /category/resources/decisions/supreme-court-decisions/        77 pages
    /category/resources/decisions/high-court-decisions/          164 pages
    /category/resources/decisions/court-of-appeal-decisions/     105 pages
    /category/resources/decisions/constitutional-court-decisions/ 24 pages
    /category/resources/decisions/subordinate-court-decisions/    14 pages

This walks those archives instead.

Two things it does that the sitemap harvester cannot:

  * Records WHICH COURT decided the case. The old script stamped every
    judgment "Issued by: Judiciary of Zambia", so nothing downstream could
    tell a Supreme Court authority from a Subordinate Court one. That
    distinction is the whole point of precedent. Court now comes from the
    archive the case was found in, which is authoritative, rather than
    being guessed from the filename.
  * Walks pages, so coverage is bounded by politeness rather than by what
    happens to be in a sitemap.

SOURCES: judiciaryzambia.com only, whose robots.txt disallows just
/wp-admin/. ZambiaLII is NOT used and must not be: it forbids scraping.
Zambia Law Reports are not used either.

Politeness: every HTTP request is delayed (--delay, default 1.0s), not just
the ingest steps. Bounded by --limit and --max-pages. Idempotent: a PDF
already ingested (by canonical_url) is skipped, so re-running resumes.

Usage:
  # look first, ingest nothing
  backend/.venv/bin/python scripts/harvest_court_decisions.py \
      --court supreme --max-pages 2 --dry-run

  # bounded real run
  backend/.venv/bin/python scripts/harvest_court_decisions.py \
      --court supreme --limit 25 --max-pages 5
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.parse
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

# Reuse the proven pieces rather than reimplementing them: filename ->
# title/citation parsing, storage upload, page counting, area inference.
from harvest_judiciary_judgments import (  # noqa: E402
    BASE, DOWNLOAD_DIR, derive, infer_area, pages_of, slug, upload,
)

sys.path.insert(0, str(REPO / "backend"))
from app.db.supabase import get_db  # noqa: E402
from app.services.form_ingester import ingest_form_pdf  # noqa: E402

# The archive slug is the authority on which court decided the case, so the
# court label is taken from here rather than guessed from a filename.
COURTS = {
    "supreme": ("supreme-court-decisions", "Supreme Court of Zambia"),
    "appeal": ("court-of-appeal-decisions", "Court of Appeal of Zambia"),
    "constitutional": ("constitutional-court-decisions", "Constitutional Court of Zambia"),
    "high": ("high-court-decisions", "High Court of Zambia"),
    "subordinate": ("subordinate-court-decisions", "Subordinate Court of Zambia"),
}

CAT_ROOT = f"{BASE}/category/resources/decisions"

# Listing pages link to plenty that is not a decision.
SKIP_POST = re.compile(
    r"/(category|tag|author|page|wp-|feed|about|contact|news|event|cause-?list|"
    r"vacanc|tender|procurement|speech|press|gallery|charter|strategic|"
    r"annual-report|practice-direction|holiday|notice|administration-of-)",
    re.I,
)


def client() -> httpx.Client:
    return httpx.Client(
        timeout=45, follow_redirects=True, verify=False,
        headers={"User-Agent": "Mozilla/5.0 (compatible; LevyResearch/1.0; +https://levylegal.ai)"},
    )


def listing_pages(c: httpx.Client, slug_name: str, max_pages: int, delay: float):
    """Yield (page_number, html) for the archive, stopping when it runs out."""
    for n in range(1, max_pages + 1):
        url = f"{CAT_ROOT}/{slug_name}/" if n == 1 else f"{CAT_ROOT}/{slug_name}/page/{n}/"
        try:
            r = c.get(url)
        except Exception as e:  # noqa: BLE001
            print(f"  ! page {n}: {str(e)[:70]}")
            return
        time.sleep(delay)
        if r.status_code != 200:
            return
        yield n, r.text


def post_links(html: str) -> list[str]:
    out, seen = [], set()
    for href in re.findall(r'href="(https://judiciaryzambia\.com/[^"]+)"', html):
        href = href.split("#")[0]
        if not href.endswith("/") or SKIP_POST.search(href):
            continue
        # a decision post lives at the site root, not under a section path
        if href.count("/") != 4 or href in seen:
            continue
        seen.add(href)
        out.append(href)
    return out


def pdf_on_post(c: httpx.Client, post_url: str, delay: float) -> str | None:
    try:
        r = c.get(post_url)
    except Exception:
        return None
    time.sleep(delay)
    if r.status_code != 200:
        return None
    pdfs = re.findall(r'href=["\']([^"\']+\.pdf)["\']', r.text, re.I)
    # Only the Judiciary's own media. Never ZambiaLII, even if a page links it.
    cands = [p for p in pdfs if "/uploads/" in p or "judiciaryzambia" in p]
    if not cands:
        return None
    return urllib.parse.urljoin(post_url, cands[0])


# A decision archive page also links its own menu and sidebar, which is how
# "The Court of Appeal Act", "The Constitutional Court Act" and an office
# contacts page turned up in the first dry run. A real judgment carries either
# a court citation or a "v"/"vs" between parties, so require one of those in
# the PDF name before ingesting. Cheap, and it fails closed: a judgment with an
# unusual filename is skipped rather than a statute being filed as case law.
JUDGMENT_SHAPE = re.compile(
    r"(\b(scz|app|caz|ccz|hp|hpf|hpa|hk|hn|hj|hc)\b[-_ ]?\d"   # citation
    r"|[-_ ]vs?[-_ ]"                                            # A v B
    r"|\bcoram\b|\bjustice\b)",                                # bench named
    re.I,
)


# The archive a case is filed under is NOT reliable evidence of which court
# decided it: the Supreme Court archive also links CCZ (Constitutional Court)
# and HPF (High Court, Family) decisions. Labelling a High Court decision as
# Supreme Court authority would misstate precedent weight to a practitioner,
# which is the single most damaging error this harvester could make. So the
# court is read from the CITATION, which is authoritative, and the archive is
# used only when the citation cannot settle it.
#
#   SCZ  Supreme Court        CCZ  Constitutional Court
#   CAZ  Court of Appeal      HP/HPF/HPA/HK/HN/HJ/HB  High Court
#   APP  ambiguous: both the Supreme Court and the Court of Appeal number
#        appeals "APP No.", so fall back to the bench or the archive.
#
# Bench suffixes are a good secondary signal: JJS sit in the Supreme Court,
# JJA in the Court of Appeal, JJC in the Constitutional Court, and only the
# Supreme Court has a Chief Justice sitting as CJ.
CITATION_COURT = [
    (re.compile(r"\bSCZ\b", re.I), "Supreme Court of Zambia"),
    (re.compile(r"\bCCZ\b", re.I), "Constitutional Court of Zambia"),
    (re.compile(r"\bCAZ\b", re.I), "Court of Appeal of Zambia"),
    (re.compile(r"\bH(PF|PA|P|K|N|J|B)\b", re.I), "High Court of Zambia"),
]
BENCH_COURT = [
    (re.compile(r"\bJJ\.?S\b|\bCJ\b|\bDCJ\b", re.I), "Supreme Court of Zambia"),
    (re.compile(r"\bJJ\.?A\b|\bDJP\b", re.I), "Court of Appeal of Zambia"),
    (re.compile(r"\bJJ\.?C\b", re.I), "Constitutional Court of Zambia"),
]


def court_of(pdf_url: str, title: str, archive_authority: str) -> tuple[str, str]:
    """Return (court, how_we_decided). Citation wins, then bench, then archive."""
    blob = urllib.parse.unquote(pdf_url.rsplit("/", 1)[-1]) + " " + title
    for pat, court in CITATION_COURT:
        if pat.search(blob):
            return court, "citation"
    for pat, court in BENCH_COURT:
        if pat.search(blob):
            return court, "bench"
    return archive_authority, "archive"


def looks_like_judgment(pdf_url: str, title: str) -> bool:
    name = urllib.parse.unquote(pdf_url.rsplit("/", 1)[-1])
    return bool(JUDGMENT_SHAPE.search(name) or JUDGMENT_SHAPE.search(title))


def already() -> set[str]:
    rows = (get_db().table("legal_documents").select("canonical_url")
            .eq("document_type", "judgment").execute()).data or []
    return {r["canonical_url"] for r in rows if r.get("canonical_url")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--court", default="supreme",
                    choices=[*COURTS.keys(), "all"])
    ap.add_argument("--limit", type=int, default=25, help="max judgments to INGEST")
    ap.add_argument("--max-pages", type=int, default=5, help="max archive pages to walk")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between HTTP requests")
    ap.add_argument("--dry-run", action="store_true",
                    help="discover and report only; download and ingest nothing")
    args = ap.parse_args()

    courts = list(COURTS) if args.court == "all" else [args.court]
    have = already()
    print(f"Already hold {len(have)} judgments (by canonical_url).")
    print(f"Mode: {'DRY RUN, nothing will be written' if args.dry_run else 'INGEST'}  "
          f"limit={args.limit} max_pages={args.max_pages} delay={args.delay}s\n")

    ingested = seen_posts = found_pdfs = skipped = failed = rejected = reclassified = 0
    by_source: dict[str, int] = {}

    with client() as c:
        for court_key in courts:
            slug_name, authority = COURTS[court_key]
            print(f"=== {authority}  ({slug_name}) ===")
            for page_no, html in listing_pages(c, slug_name, args.max_pages, args.delay):
                links = post_links(html)
                print(f"  page {page_no}: {len(links)} candidate posts")
                for post in links:
                    if ingested >= args.limit:
                        print("  reached --limit")
                        break
                    seen_posts += 1
                    pdf = pdf_on_post(c, post, args.delay)
                    if not pdf:
                        continue
                    found_pdfs += 1
                    if pdf in have:
                        skipped += 1
                        continue
                    title, citation = derive(pdf, b"")
                    if not looks_like_judgment(pdf, title):
                        rejected += 1
                        if args.dry_run:
                            print(f"    skip (not a judgment): {title[:60]}")
                        continue
                    court, how = court_of(pdf, title, authority)
                    if how != "archive":
                        by_source[how] = by_source.get(how, 0) + 1
                    else:
                        by_source["archive"] = by_source.get("archive", 0) + 1
                    if court != authority:
                        reclassified += 1
                    if args.dry_run:
                        flag = "" if court == authority else "  <-- NOT this archive's court"
                        print(f"    would ingest: [{court}] ({how}) {title[:56]}{flag}")
                        have.add(pdf)
                        ingested += 1
                        continue
                    try:
                        r = c.get(pdf)
                        time.sleep(args.delay)
                    except Exception:
                        failed += 1
                        continue
                    content = r.content
                    if (r.status_code != 200 or not content.startswith(b"%PDF")
                            or len(content) < 20_000):
                        continue
                    area = infer_area(title)
                    key = slug(title) + ".pdf"
                    local = DOWNLOAD_DIR / key
                    local.write_bytes(content)
                    desc = (f"Zambian court judgment ({area} law) decided by the "
                            f"{court}." + (f" Citation: {citation}." if citation else "")
                            + " Published by the Judiciary of Zambia.")
                    try:
                        res = ingest_form_pdf(
                            str(local), title=title,
                            short_name=(citation or title)[:80], description=desc,
                            document_type="judgment", category=area,
                            # The COURT, not the generic "Judiciary of Zambia".
                            # This lands in the header chunk, so retrieval can
                            # see whether an authority binds or persuades.
                            issuing_authority=court, source_url=pdf,
                        )
                    except Exception as e:  # noqa: BLE001
                        print(f"    ! ingest: {str(e)[:80]}")
                        failed += 1
                        continue
                    if res["status"] == "skipped":
                        skipped += 1
                        continue
                    try:
                        sp = upload(content, key)
                        get_db().table("legal_documents").update({
                            "is_global": True, "owner_id": None, "pdf_storage_path": sp,
                            "pdf_page_count": pages_of(content), "pdf_size_bytes": len(content),
                            "canonical_url": pdf, "document_type": "judgment",
                        }).eq("id", res["document"]["id"]).execute()
                    except Exception as e:  # noqa: BLE001
                        print(f"    ! storage: {str(e)[:80]}")
                        failed += 1
                        continue
                    have.add(pdf)
                    ingested += 1
                    print(f"    [{ingested}/{args.limit}] ({area}) {title[:62]}")
                if ingested >= args.limit:
                    break
            if ingested >= args.limit:
                break

    print(f"\nSUMMARY posts_visited={seen_posts} pdfs_found={found_pdfs} "
          f"ingested={ingested} skipped={skipped} rejected={rejected} failed={failed}")
    print(f"        court decided by: {by_source}   reclassified_off_archive={reclassified}")
    if args.dry_run:
        print("DRY RUN: nothing was downloaded or written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
