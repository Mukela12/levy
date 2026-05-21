#!/usr/bin/env python3
"""
Scrape + ingest landmark Zambian JUDGMENTS into the global library so the
agent can cite real binding precedent instead of reasoning in the abstract.

SOURCING POLICY (important):
  - We ONLY pull judgments from judiciaryzambia.com — the Judiciary of
    Zambia's OWN published PDFs (its robots.txt is empty / unrestricted).
  - We DO NOT scrape zambialii.org: its robots.txt explicitly disallows
    AI crawlers + /akn/zm/judgment/ and reserves EU copyright rights.
    For the long tail, the chat agent cites ZambiaLII at query-time via
    gov_search/web_fetch (fair-use citation, not bulk ingestion).

For each landmark case we:
  1. Tavily-search judiciaryzambia.com for the judgment PDF.
  2. Download it (court's own publication).
  3. Ingest with document_type='judgment', tagging court + area so the
     agent can filter precedent by topic.
  4. Upload to Supabase storage + mark is_global so it's citable +
     downloadable.

Idempotent: PDFs hashed, re-runs skip what's already in.

Usage:
  /Users/mukelakatungu/levy/.claude/worktrees/lucid-bartik-c2ad7f/.venv/bin/python \
      scripts/scrape_and_ingest_zambian_caselaw.py
"""

from __future__ import annotations

import io
import os
import re
import sys
import time
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

DOWNLOAD_DIR = Path("/Users/mukelakatungu/levy-test-fixtures/zambian-caselaw")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
BUCKET = "legal-docs"

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
if not TAVILY_API_KEY:
    print("TAVILY_API_KEY empty. Aborting.")
    sys.exit(1)

# Only the court's own site. (No zambialii — see policy note above.)
COURT_DOMAINS = ["judiciaryzambia.com", "www.judiciaryzambia.com"]

# Landmark / instructive Zambian cases by area. We search broadly because
# the exact PDF filenames on judiciaryzambia.com are unpredictable; we keep
# whatever genuine judgment PDFs come back. `area` tags the precedent so the
# agent can pull "employment cases" vs "land cases".
CASES: list[dict] = [
    {"area": "employment", "queries": [
        "Gildah Ngoma World Vision Zambia judgment Court of Appeal PDF",
        "unfair dismissal Court of Appeal Zambia judgment Employment Code Act PDF",
    ]},
    {"area": "employment", "queries": [
        "Zambia Consolidated Copper Mines Matale judgment PDF judiciary",
        "wrongful dismissal Supreme Court Zambia judgment PDF",
    ]},
    {"area": "employment", "queries": [
        "Swarp Spinning Mills Sebastian Chileshe judgment Zambia PDF",
        "redundancy terminal benefits Court of Appeal Zambia judgment PDF",
    ]},
    {"area": "land", "queries": [
        "specific performance sale of land Zambia judgment PDF judiciary",
        "customary land conversion leasehold Zambia judgment Court of Appeal PDF",
    ]},
    {"area": "land", "queries": [
        "certificate of title fraud Lands and Deeds Registry Zambia judgment PDF",
        "trespass to land Zambia High Court judgment PDF judiciary",
    ]},
    {"area": "contract", "queries": [
        "breach of contract damages Zambia Court of Appeal judgment PDF",
        "Zambia contract law judgment consideration PDF judiciary",
    ]},
    {"area": "company", "queries": [
        "Companies Act 2017 Zambia judgment director duties PDF judiciary",
        "winding up insolvency Zambia Court of Appeal judgment PDF",
    ]},
    {"area": "constitutional", "queries": [
        "Christine Mulundika People Zambia constitutional judgment PDF",
        "bill of rights freedom Zambia Constitutional Court judgment PDF judiciary",
    ]},
    {"area": "constitutional", "queries": [
        "Roy Clarke Attorney General Zambia judgment freedom expression PDF",
        "judicial review administrative decision Zambia judgment PDF judiciary",
    ]},
    {"area": "family", "queries": [
        "matrimonial property division Zambia Court of Appeal judgment PDF",
        "custody children best interests Zambia judgment PDF judiciary",
    ]},
    {"area": "succession", "queries": [
        "letters of administration intestate estate Zambia judgment PDF",
        "wills testate estates Zambia Court of Appeal judgment PDF judiciary",
    ]},
    {"area": "criminal", "queries": [
        "Zambia Supreme Court criminal appeal judgment PDF judiciary",
        "murder conviction appeal Zambia Court of Appeal judgment PDF",
    ]},
    {"area": "tax", "queries": [
        "Zambia Revenue Authority tax appeal judgment PDF judiciary",
        "property transfer tax Zambia judgment PDF",
    ]},
    {"area": "tort", "queries": [
        "negligence personal injury damages Zambia judgment PDF judiciary",
        "defamation Zambia Court of Appeal judgment PDF",
    ]},
    {"area": "commercial", "queries": [
        "Zambia Commercial Court judgment banking PDF judiciary",
        "guarantee indemnity Zambia Court of Appeal judgment PDF",
    ]},
]


# ── helpers ─────────────────────────────────────────────────────────────────


def tavily_search(query: str, include_domains: list[str] | None = None, max_results: int = 8) -> list[dict]:
    payload = {"api_key": TAVILY_API_KEY, "query": query, "search_depth": "advanced", "max_results": max_results}
    if include_domains:
        payload["include_domains"] = include_domains
    try:
        r = httpx.post("https://api.tavily.com/search", json=payload, timeout=30)
        return (r.json() or {}).get("results", []) if r.status_code == 200 else []
    except Exception as e:  # noqa: BLE001
        print(f"    tavily error: {e}")
        return []


def pick_judgment_pdf(results: list[dict], seen_urls: set[str]) -> str | None:
    cands: list[tuple[int, str]] = []
    for r in results:
        url = (r.get("url") or "").strip()
        if not url or not url.lower().endswith(".pdf") or url in seen_urls:
            continue
        if "judiciaryzambia.com" not in url:
            continue
        score = 5
        low = url.lower()
        # Court-of-appeal / supreme-court docket markers boost confidence
        # this is a judgment, not an annual report / charter.
        if any(k in low for k in ("app-", "appeal", "scz", "judgment", "-vs-", "-v-", "coram")):
            score += 4
        if any(k in low for k in ("annual-report", "charter", "strategic", "newsletter", "brochure")):
            score -= 6
        cands.append((score, url))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0], reverse=True)
    top_score, top_url = cands[0]
    return top_url if top_score > 0 else None


def derive_case_name(url: str, content: bytes) -> tuple[str, str | None]:
    """Best-effort: produce a human case title + neutral-ish citation from the
    PDF filename and first page. judiciaryzambia.com filenames look like
    'APP-159-2020-Gildah-Ngoma-Others-vs-World-Vision-Zambia-Coram-...pdf'."""
    import urllib.parse
    fname = urllib.parse.unquote(url.rsplit("/", 1)[-1].rsplit(".", 1)[0])
    # docket like APP-159-2020
    m = re.search(r"(APP|SCZ|CAZ|CCZ)[-_ ]?(\d+)[-_ ]?(\d{4})", fname, re.I)
    citation = None
    if m:
        kind, num, year = m.group(1).upper(), m.group(2), m.group(3)
        citation = f"{kind} No. {num} of {year}"
    # party block: take text before 'Coram' and after the docket
    raw = re.sub(r"(APP|SCZ|CAZ|CCZ)[-_ ]?\d+[-_ ]?\d{4}", "", fname, flags=re.I)
    raw = re.split(r"[-_ ]?Coram", raw, flags=re.I)[0]
    name = re.sub(r"[-_]+", " ", raw).strip()
    name = re.sub(r"\bvs\b", "v", name, flags=re.I).strip()
    if not name:
        # fall back to first line of the PDF text
        try:
            from pypdf import PdfReader
            first = (PdfReader(io.BytesIO(content)).pages[0].extract_text() or "")[:120]
            name = " ".join(first.split())[:80] or fname
        except Exception:
            name = fname
    title = name if not citation else f"{name} ({citation})"
    return title[:160], citation


def slugify(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return (base or uuid.uuid4().hex)[:80]


def upload_pdf_to_storage(content: bytes, slug: str) -> str:
    db = get_db()
    key = slug
    try:
        db.storage.from_(BUCKET).upload(path=key, file=content,
            file_options={"content-type": "application/pdf", "upsert": "true"})
    except Exception as e:  # noqa: BLE001
        if "exists" in str(e).lower() or "duplicate" in str(e).lower():
            try:
                db.storage.from_(BUCKET).remove([key])
            except Exception:
                pass
            db.storage.from_(BUCKET).upload(path=key, file=content,
                file_options={"content-type": "application/pdf"})
        else:
            raise
    return f"{BUCKET}/{key}"


def patch_global(document_id: str, storage_path: str, pages: int, size: int, url: str) -> None:
    get_db().table("legal_documents").update({
        "is_global": True, "owner_id": None,
        "pdf_storage_path": storage_path, "pdf_page_count": pages,
        "pdf_size_bytes": size, "canonical_url": url, "document_type": "judgment",
    }).eq("id", document_id).execute()


def download(url: str) -> bytes | None:
    try:
        r = httpx.get(url, timeout=60, follow_redirects=True, verify=False,
                      headers={"User-Agent": "Mozilla/5.0 LevyIngest/1.0"})
    except Exception as e:  # noqa: BLE001
        print(f"    download error: {e}")
        return None
    if r.status_code != 200 or not r.content.startswith(b"%PDF") or len(r.content) < 20_000:
        print(f"    rejected (status={r.status_code}, bytes={len(r.content)})")
        return None
    return r.content


def page_count(content: bytes) -> int:
    try:
        from pypdf import PdfReader
        return len(PdfReader(io.BytesIO(content)).pages)
    except Exception:
        return 0


def main() -> int:
    seen_urls: set[str] = set()
    results: list[dict] = []

    for i, case in enumerate(CASES, 1):
        area = case["area"]
        print("\n" + "=" * 78)
        print(f"  [{i}/{len(CASES)}] area={area}")
        print("=" * 78)

        url = None
        for q in case["queries"]:
            url = pick_judgment_pdf(tavily_search(q, include_domains=COURT_DOMAINS), seen_urls)
            if url:
                break
        if not url:
            print("  ! no judgment PDF found on judiciaryzambia.com")
            results.append({"area": area, "status": "no_url"})
            continue
        seen_urls.add(url)
        print(f"    found: {url}")

        content = download(url)
        if content is None:
            results.append({"area": area, "status": "download_failed"})
            continue
        print(f"    {len(content):,} bytes")

        title, citation = derive_case_name(url, content)
        print(f"    title: {title}")

        slug = slugify(title) + ".pdf"
        local = DOWNLOAD_DIR / slug
        local.write_bytes(content)

        desc = (
            f"Zambian court judgment ({area} law). "
            + (f"Citation: {citation}. " if citation else "")
            + "Published by the Judiciary of Zambia. Cite this as binding or "
            "persuasive precedent according to the issuing court's place in "
            "the hierarchy."
        )
        try:
            ing = ingest_form_pdf(
                str(local),
                title=title,
                short_name=(citation or title)[:80],
                description=desc,
                document_type="judgment",
                category=area,
                issuing_authority="Judiciary of Zambia",
                source_url=url,
            )
        except Exception as e:  # noqa: BLE001
            print(f"  ! ingest error: {e}")
            results.append({"area": area, "status": "ingest_failed"})
            continue

        if ing["status"] == "skipped":
            results.append({"area": area, "status": "skipped"})
            continue

        doc_id = ing["document"]["id"]
        try:
            sp = upload_pdf_to_storage(content, slug)
            patch_global(doc_id, sp, page_count(content), len(content), url)
            print(f"    → {sp}")
        except Exception as e:  # noqa: BLE001
            print(f"  ! storage error: {e}")
            results.append({"area": area, "status": "storage_failed"})
            continue

        results.append({"area": area, "status": "ok", "title": title, "url": url})
        time.sleep(1)

    print("\n\n" + "=" * 78 + "\n  SUMMARY\n" + "=" * 78)
    by = {}
    for r in results:
        by[r["status"]] = by.get(r["status"], 0) + 1
    for k, n in sorted(by.items()):
        print(f"  {k:16s} {n}")
    print("\n  Ingested cases:")
    for r in results:
        if r["status"] == "ok":
            print(f"    [{r['area']:13s}] {r['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
