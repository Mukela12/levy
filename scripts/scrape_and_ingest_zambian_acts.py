#!/usr/bin/env python3
"""
Scrape canonical PDFs for the major Zambian statutes (Constitution, Penal
Code, Companies Act, etc.) and ingest them into the production global
library.

Source discovery uses Tavily restricted to a whitelist of Zambian gov /
institutional domains (parliament.gov.zm, lawsofzambia.com, zambialii.org,
moj.gov.zm, etc.). For each Act we:

  1. Tavily-search a few likely query phrasings; pick the first .pdf URL
     that looks like the canonical Act text (not a commentary or summary).
  2. Download it.
  3. Run it through the existing ingest pipeline (parse → chunk →
     OpenAI 768-d embeddings → legal_chunks).
  4. Patch the legal_documents row so the doc is marked is_global=true
     and its storage path / page count is set, exactly like manual upload.

Idempotent: every PDF is hashed and skipped if already in the table.

Usage:
  /Users/mukelakatungu/levy/.claude/worktrees/lucid-bartik-c2ad7f/.venv/bin/python \
      scripts/scrape_and_ingest_zambian_acts.py
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import sys
import time
import uuid
from pathlib import Path

import httpx
import warnings
# We intentionally use verify=False for downloads from gov sites with
# misconfigured cert chains. Mute the per-request warning so the script's
# output stays readable.
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
from app.services.ingester import ingest_pdf  # noqa: E402

# ── Config ───────────────────────────────────────────────────────────────────

DOWNLOAD_DIR = Path("/Users/mukelakatungu/levy-test-fixtures/zambian-acts")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

BUCKET = "legal-docs"

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
if not TAVILY_API_KEY:
    print("TAVILY_API_KEY is empty in backend/.env. Aborting.")
    sys.exit(1)

# Whitelist of Zambian gov / institutional sources. Tavily restricts
# `include_domains` to these. zambialii.org has the broadest free coverage of
# Zambian Acts in PDF form; the rest are the actual gov publishers.
GOV_DOMAINS = [
    "parliament.gov.zm",
    "zambialii.org",
    "lawsofzambia.com",
    "moj.gov.zm",
    "zambia.gov.zm",
    "judiciaryzambia.com",
    "pacra.org.zm",
    "minfin.gov.zm",
    "zra.org.zm",
    "boz.zm",
    "zppa.org.zm",
    "eprocure.zppa.org.zm",
]

# Acts to ingest. The list is intentionally tilted toward statutes a working
# Zambian lawyer / founder / public-interest user is most likely to ask about.
ACTS: list[dict] = [
    {"title": "Constitution of Zambia (Amendment) Act, 2016", "queries": [
        "Constitution of Zambia Amendment Act No 2 of 2016 PDF",
        "Zambia Constitution 2016 PDF text",
    ]},
    {"title": "Penal Code Act (Cap 87)", "queries": [
        "Zambia Penal Code Cap 87 PDF",
        "Penal Code of Zambia PDF",
    ]},
    {"title": "Criminal Procedure Code Act (Cap 88)", "queries": [
        "Zambia Criminal Procedure Code Cap 88 PDF",
    ]},
    {"title": "Companies Act, 2017", "queries": [
        "Companies Act No 10 of 2017 Zambia PDF",
        "Zambia Companies Act 2017 text PDF",
    ]},
    {"title": "Income Tax Act (Cap 323)", "queries": [
        "Income Tax Act Cap 323 Zambia PDF",
    ]},
    {"title": "Value Added Tax Act (Cap 331)", "queries": [
        "Value Added Tax Act Cap 331 Zambia PDF",
    ]},
    {"title": "Customs and Excise Act (Cap 322)", "queries": [
        "Customs and Excise Act Cap 322 Zambia PDF",
    ]},
    {"title": "Banking and Financial Services Act, 2017", "queries": [
        "Banking and Financial Services Act 2017 Zambia PDF",
    ]},
    {"title": "Lands Act (Cap 184)", "queries": [
        "Lands Act Cap 184 Zambia PDF",
    ]},
    {"title": "Lands and Deeds Registry Act (Cap 185)", "queries": [
        "Lands and Deeds Registry Act Cap 185 Zambia PDF",
    ]},
    {"title": "Public Procurement Act, 2008", "queries": [
        "Public Procurement Act 2008 Zambia PDF",
        "Zambia Public Procurement Act No 12 of 2008 PDF",
    ]},
    {"title": "Local Government Act, 2019", "queries": [
        "Local Government Act 2019 Zambia PDF",
    ]},
    {"title": "Electoral Process Act, 2016", "queries": [
        "Electoral Process Act 2016 Zambia PDF",
    ]},
    {"title": "Cyber Security and Cyber Crimes Act, 2021", "queries": [
        "Cyber Security and Cyber Crimes Act 2021 Zambia PDF",
    ]},
    {"title": "Data Protection Act, 2021", "queries": [
        "Data Protection Act 2021 Zambia PDF",
    ]},
    {"title": "Anti-Corruption Act, 2012", "queries": [
        "Anti Corruption Act 2012 Zambia PDF",
    ]},
    {"title": "Children's Code Act, 2022", "queries": [
        "Children Code Act 2022 Zambia PDF",
    ]},
    {"title": "Industrial and Labour Relations Act (Cap 269)", "queries": [
        "Industrial and Labour Relations Act Cap 269 Zambia PDF",
    ]},
    {"title": "Workers' Compensation Act (Cap 271)", "queries": [
        "Workers Compensation Act Zambia PDF",
    ]},
    {"title": "Insurance Act, 1997", "queries": [
        "Insurance Act 1997 Zambia PDF",
    ]},
    {"title": "Securities Act, 2016", "queries": [
        "Securities Act 2016 Zambia PDF",
    ]},
    {"title": "Citizenship Act, 2016", "queries": [
        "Citizenship of Zambia Act 2016 PDF",
    ]},
    {"title": "Marriage Act (Cap 50)", "queries": [
        "Marriage Act Cap 50 Zambia PDF",
    ]},
    {"title": "Tourism and Hospitality Act, 2015", "queries": [
        "Tourism and Hospitality Act 2015 Zambia PDF",
    ]},
    {"title": "National Health Insurance Act, 2018", "queries": [
        "National Health Insurance Act 2018 Zambia PDF",
    ]},
    {"title": "Information and Communication Technologies Act, 2009", "queries": [
        "Information and Communication Technologies Act 2009 Zambia PDF",
    ]},
    {"title": "Citizen Economic Empowerment Act, 2006", "queries": [
        "Citizen Economic Empowerment Act 2006 Zambia PDF",
    ]},
    {"title": "Refugees Act, 2017", "queries": [
        "Refugees Act 2017 Zambia PDF",
    ]},
]


# ── Tavily helpers ───────────────────────────────────────────────────────────


def tavily_search(query: str, *, include_domains: list[str] | None = None, max_results: int = 8) -> list[dict]:
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
        "include_answer": False,
        "include_raw_content": False,
    }
    if include_domains:
        payload["include_domains"] = include_domains
    try:
        r = httpx.post("https://api.tavily.com/search", json=payload, timeout=30)
    except Exception as e:  # noqa: BLE001
        print(f"    Tavily error: {e}")
        return []
    if r.status_code != 200:
        print(f"    Tavily {r.status_code}: {r.text[:120]}")
        return []
    return r.json().get("results", []) or []


# Words in the URL path that flag a PDF as commentary / opinion / press
# release / blog rather than the canonical Act text.
COMMENTARY_BLACKLIST = re.compile(
    r"(?i)/(?:policy-brief|commentary|opinion|analysis|summary|explainer|"
    r"guide|press|news|blog|newsletter|report|review|paper|brief|articles)/?|"
    r"-(?:summary|explainer|analysis|brief|commentary|guide)-",
)

# ZambiaLII canonical Act URLs end with "/source" (which redirects to the
# actual PDF). We accept these even though they don't have a .pdf suffix.
# Statutory Instruments (path contains "/act/si/") are NOT the parent Act,
# so we still reject those — we want the full Act text, not an SI.
ZAMBIALII_SOURCE = re.compile(r"^https?://(?:www\.)?(?:media\.)?zambialii\.org/akn/zm/act/(?!si/)[^?#]*?/source(?:\?.*)?$", re.IGNORECASE)

# Hostnames we trust most for canonical Act text. Higher priority = picked first.
HOST_PRIORITY = [
    "zambialii.org",
    "media.zambialii.org",
    "parliament.gov.zm",
    "lawsofzambia.com",
    "moj.gov.zm",
    "zambia.gov.zm",
]


def _score_url(u: str) -> int:
    """Higher is better. Negative if the URL looks like commentary."""
    if COMMENTARY_BLACKLIST.search(u):
        return -1000
    score = 0
    lower = u.lower()
    # PDF-ness (direct .pdf wins, ZambiaLII /source is a close second)
    if lower.endswith(".pdf"):
        score += 50
    elif ZAMBIALII_SOURCE.match(u):
        score += 45
    # Trusted host
    for i, host in enumerate(HOST_PRIORITY):
        if host in lower:
            score += 100 - i * 5
            break
    # Looks like the Act text (path contains 'act', 'cap', or 'code')
    if re.search(r"/(?:act|cap|code)[s_/-]", lower):
        score += 10
    return score


def _is_likely_pdf(u: str) -> bool:
    return u.lower().endswith(".pdf") or bool(ZAMBIALII_SOURCE.match(u))


def pick_pdf_url(results: list[dict]) -> str | None:
    """Choose the most likely-canonical PDF among Tavily results."""
    candidates: list[tuple[int, str]] = []
    for r in results:
        u = (r.get("url") or "").strip()
        if u and _is_likely_pdf(u):
            candidates.append((_score_url(u), u))
        c = r.get("content") or ""
        for m in re.finditer(r"https?://[^\s\"'<>]+\.pdf", c):
            candidates.append((_score_url(m.group(0)), m.group(0)))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    top_score, top_url = candidates[0]
    if top_score <= 0:
        return None
    return top_url


def find_pdf_url(act: dict) -> str | None:
    for q in act["queries"]:
        # Restricted to gov / institutional domains first
        url = pick_pdf_url(tavily_search(q, include_domains=GOV_DOMAINS))
        if url:
            return url
        # Open web fallback, still scored / filtered the same way
        url = pick_pdf_url(tavily_search(q))
        if url:
            return url
    return None


def looks_like_the_act(content: bytes, title: str) -> bool:
    """Reject obvious-non-Acts before they hit the ingester.

    Checks:
      - At least 8 pages (real Acts are longer; SIs and amendments are short).
      - Title keywords actually appear in the first ~3 pages of text.
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        pages = len(reader.pages)
        if pages < 8:
            print(f"    only {pages} pages; likely an SI / amendment, not the parent Act.")
            return False
        first = " ".join(page.extract_text() or "" for page in reader.pages[: min(3, pages)])
    except Exception:
        return True  # don't reject on parse error; let ingester decide
    if not first.strip():
        return True
    lower = first.lower()
    title_words = re.findall(r"[A-Za-z]{4,}", title)
    keep = [w.lower() for w in title_words if w.lower() not in {"act", "code", "of", "and", "cap", "the", "from"}]
    if not keep:
        return True
    matched = sum(1 for w in keep if w in lower)
    if matched < max(1, len(keep) // 2):
        print(f"    title-word match too low ({matched}/{len(keep)}); rejecting.")
        return False
    return True


# ── Download + ingest ────────────────────────────────────────────────────────


def slugify(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return base or uuid.uuid4().hex


def pdf_already_ingested(pdf_hash: str) -> dict | None:
    res = (
        get_db()
        .table("legal_documents")
        .select("id, title, total_chunks, is_global")
        .eq("pdf_hash", pdf_hash)
        .execute()
    )
    return res.data[0] if res.data else None


def upload_pdf_to_storage(content: bytes, slug: str) -> str:
    db = get_db()
    key = slug
    try:
        db.storage.from_(BUCKET).upload(
            path=key,
            file=content,
            file_options={"content-type": "application/pdf", "upsert": "true"},
        )
    except Exception as e:  # noqa: BLE001
        if "exists" in str(e).lower() or "duplicate" in str(e).lower():
            try:
                db.storage.from_(BUCKET).remove([key])
            except Exception:
                pass
            db.storage.from_(BUCKET).upload(
                path=key,
                file=content,
                file_options={"content-type": "application/pdf"},
            )
        else:
            raise
    return f"{BUCKET}/{key}"


def patch_global_metadata(document_id: str, storage_path: str, page_count: int, size_bytes: int, canonical_url: str | None) -> None:
    patch = {
        "is_global": True,
        "owner_id": None,
        "pdf_storage_path": storage_path,
        "pdf_page_count": page_count,
        "pdf_size_bytes": size_bytes,
    }
    if canonical_url:
        patch["canonical_url"] = canonical_url
    get_db().table("legal_documents").update(patch).eq("id", document_id).execute()


def download(url: str) -> bytes | None:
    # Several Zambian gov hosts (notably parliament.gov.zm) serve an
    # incomplete certificate chain that the macOS/certifi bundle won't
    # validate. The content is a public PDF; relax verification rather
    # than skip the whole site.
    try:
        r = httpx.get(
            url,
            timeout=60,
            follow_redirects=True,
            verify=False,
            headers={"User-Agent": "Mozilla/5.0 LevyIngest/1.0"},
        )
    except Exception as e:  # noqa: BLE001
        print(f"    download error: {e}")
        return None
    if r.status_code != 200:
        print(f"    download {r.status_code}")
        return None
    if not r.content or len(r.content) < 50_000:
        # A real Act PDF is rarely under 50 KB. Tiny PDFs are usually a
        # Statutory Instrument or amendment, not the parent Act.
        print(f"    suspiciously small ({len(r.content)} bytes); rejecting.")
        return None
    if not r.content.startswith(b"%PDF"):
        print(f"    not a PDF (magic bytes={r.content[:8]!r})")
        return None
    return r.content


def main() -> int:
    results: list[dict] = []

    for i, act in enumerate(ACTS, 1):
        title = act["title"]
        print("\n" + "=" * 78)
        print(f"  [{i}/{len(ACTS)}] {title}")
        print("=" * 78)

        # Step 1 — discover PDF URL
        print("  Searching for canonical PDF…")
        url = find_pdf_url(act)
        if not url:
            print("    ✗ no PDF found.")
            results.append({"title": title, "status": "no-pdf"})
            continue
        print(f"    found: {url}")

        # Step 2 — download
        slug = slugify(title) + ".pdf"
        path = DOWNLOAD_DIR / slug
        if path.exists():
            print(f"    re-using cached: {path.name}")
            content = path.read_bytes()
        else:
            print("    downloading…")
            content = download(url)
            if not content:
                results.append({"title": title, "status": "download-failed", "url": url})
                continue
            path.write_bytes(content)
        size_bytes = len(content)

        # Step 2b — confirm the PDF text mentions the Act we asked for.
        # Tavily sometimes lets policy-brief / summary PDFs through that
        # the URL filter doesn't catch.
        if not looks_like_the_act(content, title):
            print("    ✗ PDF text doesn't match title; rejecting.")
            try:
                path.unlink()
            except Exception:
                pass
            results.append({"title": title, "status": "rejected-not-the-act", "url": url})
            continue

        # Step 3 — dedupe
        pdf_hash = hashlib.sha256(content).hexdigest()
        existing = pdf_already_ingested(pdf_hash)
        if existing:
            print(f"    already ingested (doc {existing['id']}, {existing.get('total_chunks')} chunks). Skipping.")
            # Still backfill is_global = true if it wasn't.
            if not existing.get("is_global"):
                get_db().table("legal_documents").update({"is_global": True, "owner_id": None}).eq(
                    "id", existing["id"]
                ).execute()
                print("    backfilled is_global=true.")
            results.append({"title": title, "status": "exists", "document_id": existing["id"]})
            continue

        # Step 4 — upload to storage
        print(f"    uploading to storage: {BUCKET}/{slug} ({size_bytes / 1024:.1f} KB)")
        try:
            storage_path = upload_pdf_to_storage(content, slug)
        except Exception as e:  # noqa: BLE001
            print(f"    storage upload failed: {e}")
            results.append({"title": title, "status": f"storage-failed: {e}"})
            continue

        # Step 5 — run ingester
        print("    running ingester (parse + embed + insert)…")
        t0 = time.monotonic()
        try:
            res = ingest_pdf(str(path))
        except Exception as e:  # noqa: BLE001
            print(f"    ingest error: {e}")
            results.append({"title": title, "status": f"ingest-failed: {e}"})
            continue
        elapsed = time.monotonic() - t0

        if res.get("status") != "success":
            print(f"    ingest returned status={res.get('status')}; skipping metadata patch.")
            results.append({"title": title, "status": res.get("status", "?")})
            continue
        document = res["document"]
        doc_id = document["id"]
        # Page count
        try:
            from pypdf import PdfReader
            page_count = len(PdfReader(io.BytesIO(content)).pages)
        except Exception:
            page_count = 0

        patch_global_metadata(doc_id, storage_path, page_count, size_bytes, canonical_url=url)
        chunks = res.get("chunks_created", 0)
        sections = res.get("sections_found", 0)
        print(f"    ✓ ingested: doc {doc_id}  pages={page_count}  sections={sections}  chunks={chunks}  took={elapsed:.1f}s")
        results.append({
            "title": title,
            "status": "ingested",
            "document_id": doc_id,
            "pages": page_count,
            "chunks": chunks,
            "url": url,
        })

    print()
    print("=" * 78)
    print(" SUMMARY")
    print("=" * 78)
    statuses: dict[str, int] = {}
    for r in results:
        s = r["status"].split(":", 1)[0]
        statuses[s] = statuses.get(s, 0) + 1
        print(f"  [{r['status']:>16}] {r['title']}")
    print()
    print("  Totals:", ", ".join(f"{k}={v}" for k, v in statuses.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
