#!/usr/bin/env python3
"""
Scrape and ingest common Zambian application / government / institutional
documents into the global library, alongside the statutes already there.

Different from the Acts scraper:
  - target docs are forms, applications, guides, fee schedules — not Acts.
  - they're short (1-12 pages), don't have a Part/Section structure, and
    are usually the actual PDF a citizen / lawyer is supposed to fill in.
  - they go through `form_ingester.ingest_form_pdf`, not the Acts pipeline.

For each entry we:
  1. Tavily-search a few likely phrasings on a domain whitelist of the
     issuing authority (PACRA, ZRA, BoZ, NAPSA, Immigration, Lands, etc.)
     plus open-web fallback.
  2. Download the first PDF that looks like the actual form (loose check).
  3. Ingest with document_type='form' / 'application' / 'guide' /
     'fee_schedule' so frontend filters can group them.
  4. Upload PDF to Supabase storage + mark is_global=True so the chat
     agent can recommend + the user can download.

Idempotent: PDFs are hashed; re-runs skip what's already in.

Usage:
  /Users/mukelakatungu/levy/.claude/worktrees/lucid-bartik-c2ad7f/.venv/bin/python \
      scripts/scrape_and_ingest_zambian_forms.py
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

# ── Config ───────────────────────────────────────────────────────────────────

DOWNLOAD_DIR = Path("/Users/mukelakatungu/levy-test-fixtures/zambian-forms")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

BUCKET = "legal-docs"

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
if not TAVILY_API_KEY:
    print("TAVILY_API_KEY is empty in backend/.env. Aborting.")
    sys.exit(1)


# ── Curated form / application library ──────────────────────────────────────
#
# Each entry describes ONE Zambian document a user might need to fill in,
# download, or read alongside a statute. Keep these tilted toward the
# things small businesses, employees, foreign investors and ordinary
# citizens reach for first.
#
# Fields:
#   title              — authoritative title shown in search results
#   short_name         — what citation / artifact card uses (~40 chars)
#   description        — embedded as the first chunk so vector search hits
#                        even when the PDF is image-only / scanned
#   document_type      — 'form' | 'application' | 'guide' | 'fee_schedule'
#                      | 'checklist' | 'circular' | 'court_rule'
#   category           — coarse grouping the frontend filter can use
#   issuing_authority  — agency that publishes the form
#   domains            — Tavily include_domains whitelist; empty = open web
#   queries            — search phrasings, tried in order

FORMS: list[dict] = [
    # ─── PACRA: company registration & business names ──────────────────────
    {
        "title": "PACRA Form 5 — Application for Registration of a Private Company Limited by Shares",
        "short_name": "PACRA Form 5",
        "description": (
            "Statutory form used to incorporate a private company limited by shares with the "
            "Patents and Companies Registration Agency (PACRA). Lists the proposed company name, "
            "registered office, share capital, directors, secretary, shareholders, and articles "
            "of association. Filed under section 13 of the Companies Act, No. 10 of 2017."
        ),
        "document_type": "form",
        "category": "company",
        "issuing_authority": "Patents and Companies Registration Agency (PACRA)",
        "domains": ["pacra.org.zm"],
        "queries": [
            "PACRA Form 5 private company limited shares application PDF",
            "PACRA Companies Act 2017 Form 5 registration PDF",
        ],
    },
    {
        "title": "PACRA Business Name Registration Form",
        "short_name": "PACRA Business Name Form",
        "description": (
            "Application to register a business name (sole proprietorship or partnership) "
            "under the Registration of Business Names Act. Filed with PACRA."
        ),
        "document_type": "form",
        "category": "company",
        "issuing_authority": "PACRA",
        "domains": ["pacra.org.zm"],
        "queries": [
            "PACRA business name registration form PDF",
            "Zambia business name registration application form",
        ],
    },
    {
        "title": "PACRA Annual Return Form for Companies",
        "short_name": "PACRA Annual Return",
        "description": (
            "Annual return that every registered Zambian company must file with PACRA. "
            "Covers shareholding, directorship and registered-office changes for the year."
        ),
        "document_type": "form",
        "category": "company",
        "issuing_authority": "PACRA",
        "domains": ["pacra.org.zm"],
        "queries": [
            "PACRA annual return form companies Zambia PDF",
        ],
    },
    {
        "title": "PACRA Fee Schedule",
        "short_name": "PACRA Fees",
        "description": (
            "Current schedule of fees for PACRA services: company incorporation, name "
            "reservation, business name registration, annual returns, certified copies."
        ),
        "document_type": "fee_schedule",
        "category": "company",
        "issuing_authority": "PACRA",
        "domains": ["pacra.org.zm"],
        "queries": [
            "PACRA fee schedule PDF",
            "PACRA service fees 2024 PDF",
        ],
    },

    # ─── ZRA: tax registration, returns ────────────────────────────────────
    {
        "title": "ZRA TPIN Registration Form (Taxpayer Identification Number)",
        "short_name": "ZRA TPIN Form",
        "description": (
            "Application for a Taxpayer Identification Number (TPIN) from the Zambia Revenue "
            "Authority. Required for individuals, companies, NGOs and partnerships before they "
            "can file any return or transact with government."
        ),
        "document_type": "form",
        "category": "tax",
        "issuing_authority": "Zambia Revenue Authority (ZRA)",
        "domains": ["zra.org.zm"],
        "queries": [
            "ZRA TPIN application form PDF",
            "Zambia Revenue Authority taxpayer identification number form",
        ],
    },
    {
        "title": "ZRA VAT Registration Form",
        "short_name": "ZRA VAT Form",
        "description": (
            "Application for Value Added Tax registration with the Zambia Revenue Authority. "
            "Mandatory once annual taxable turnover exceeds the VAT threshold."
        ),
        "document_type": "form",
        "category": "tax",
        "issuing_authority": "ZRA",
        "domains": ["zra.org.zm"],
        "queries": [
            "ZRA VAT registration form PDF",
            "Zambia VAT registration application form",
        ],
    },
    {
        "title": "ZRA Pay-As-You-Earn (PAYE) Employer Registration Form",
        "short_name": "ZRA PAYE Form",
        "description": (
            "Employer registration for Pay-As-You-Earn (PAYE) with the Zambia Revenue "
            "Authority. Every employer with employees earning above the PAYE threshold must "
            "register and remit monthly."
        ),
        "document_type": "form",
        "category": "tax",
        "issuing_authority": "ZRA",
        "domains": ["zra.org.zm"],
        "queries": [
            "ZRA PAYE employer registration form PDF",
            "Zambia Pay As You Earn employer form",
        ],
    },

    # ─── Immigration: visas, work permits ──────────────────────────────────
    {
        "title": "Zambia Employment Permit Application Form",
        "short_name": "Employment Permit Form",
        "description": (
            "Application for an Employment Permit (long-stay work permit) for a non-Zambian "
            "professional. Filed with the Department of Immigration under the Immigration and "
            "Deportation Act."
        ),
        "document_type": "application",
        "category": "immigration",
        "issuing_authority": "Department of Immigration",
        "domains": ["zambiaimmigration.gov.zm", "immigration.gov.zm"],
        "queries": [
            "Zambia employment permit application form PDF",
            "Department of Immigration Zambia work permit form",
        ],
    },
    {
        "title": "Zambia Investor Permit Application Form",
        "short_name": "Investor Permit Form",
        "description": (
            "Investor permit application for foreign investors meeting the minimum investment "
            "threshold under the Zambia Development Agency Act and Immigration and Deportation "
            "Act. Allows the holder to reside and direct their investment in Zambia."
        ),
        "document_type": "application",
        "category": "immigration",
        "issuing_authority": "Department of Immigration",
        "domains": ["zambiaimmigration.gov.zm", "immigration.gov.zm"],
        "queries": [
            "Zambia investor permit application form PDF",
            "Zambia investor permit form Department of Immigration",
        ],
    },
    {
        "title": "Zambia Visitor / Visa Application Form",
        "short_name": "Zambia Visa Form",
        "description": (
            "Standard application form for visitor visas and visa-on-arrival categories "
            "issued by the Zambian Department of Immigration."
        ),
        "document_type": "application",
        "category": "immigration",
        "issuing_authority": "Department of Immigration",
        "domains": ["zambiaimmigration.gov.zm", "immigration.gov.zm"],
        "queries": [
            "Zambia visa application form PDF",
            "Zambia visitor visa form Department of Immigration",
        ],
    },

    # ─── Investment: ZDA, foreign-investor thresholds ──────────────────────
    {
        "title": "Zambia Development Agency Investor Application",
        "short_name": "ZDA Investor Application",
        "description": (
            "Application for registration as an investor. Governing law is now the "
            "Investment, Trade and Business Development Act No. 18 of 2022 (the 'ITBD Act', "
            "commenced 13 January 2023) with the Zambia Development Agency Act No. 17 of 2022 "
            "— these repealed the old ZDA Act No. 11 of 2006. Minimum investment for the full "
            "incentive package: USD 1,000,000 for a wholly foreign-owned enterprise; "
            "USD 500,000 citizen-influenced (5-25% Zambian); USD 150,000 citizen-empowered "
            "(25.1-50%); USD 100,000 citizen-owned (>=50.1%); USD 50,000 for a 100% "
            "Zambian-owned priority-sector business. These incentive thresholds are separate "
            "from the Department of Immigration's Investor's Permit thresholds (USD 250,000 "
            "new business / USD 150,000 to join an existing one) under the Immigration and "
            "Deportation Act No. 18 of 2010."
        ),
        "document_type": "application",
        "category": "investment",
        "issuing_authority": "Zambia Development Agency (ZDA)",
        "domains": ["zda.org.zm"],
        "queries": [
            "ZDA investor application form PDF",
            "Zambia Development Agency investor registration form",
        ],
    },
    {
        "title": "ZDA Investor Guide — Doing Business in Zambia",
        "short_name": "ZDA Investor Guide",
        "description": (
            "Official ZDA guide to investing in Zambia: sector overviews, the incentive "
            "regime, the MFEZ scheme, and step-by-step setup for foreign investors. Incentive "
            "thresholds are set by the Investment, Trade and Business Development Act No. 18 "
            "of 2022 (commenced Jan 2023), which repealed the ZDA Act No. 11 of 2006: the "
            "full incentive package needs USD 1,000,000 for a wholly foreign-owned enterprise "
            "(lower tiers down to USD 50,000 for a 100% Zambian-owned priority-sector "
            "business). Foreign investors hold land on 99-year leasehold; Zambia has no "
            "exchange controls so profits and dividends may be freely repatriated."
        ),
        "document_type": "guide",
        "category": "investment",
        "issuing_authority": "ZDA",
        "domains": ["zda.org.zm"],
        "queries": [
            "ZDA investor guide Zambia PDF",
            "Doing business in Zambia investor guide ZDA PDF",
        ],
    },

    # ─── Lands: title deeds, land applications ─────────────────────────────
    {
        "title": "Application for State Land Lease — Ministry of Lands",
        "short_name": "State Land Lease Application",
        "description": (
            "Form used to apply for a leasehold over state land in Zambia. Submitted to the "
            "Ministry of Lands and Natural Resources under the Lands Act, Cap 184. "
            "Successful applicants receive a Certificate of Title for a 99-year leasehold."
        ),
        "document_type": "application",
        "category": "lands",
        "issuing_authority": "Ministry of Lands and Natural Resources",
        "domains": ["mlnr.gov.zm", "lands.gov.zm"],
        "queries": [
            "Zambia state land application form Ministry of Lands PDF",
            "Zambia 99-year leasehold application form PDF",
        ],
    },
    {
        "title": "Application for Conversion of Customary Land to Leasehold",
        "short_name": "Customary Land Conversion",
        "description": (
            "Statutory procedure (under the Lands Act, Cap 184) for converting customary land "
            "held under traditional tenure into a 99-year state leasehold. Requires consent "
            "of the chief and recommendation of the local council."
        ),
        "document_type": "application",
        "category": "lands",
        "issuing_authority": "Ministry of Lands and Natural Resources",
        "domains": ["mlnr.gov.zm", "lands.gov.zm"],
        "queries": [
            "Zambia customary land conversion leasehold application PDF",
            "Conversion of customary land Zambia procedure form",
        ],
    },

    # ─── Labour / NAPSA / workers' compensation ────────────────────────────
    {
        "title": "NAPSA Employer Registration Form",
        "short_name": "NAPSA Employer Form",
        "description": (
            "National Pension Scheme Authority employer registration. Every employer with at "
            "least one employee must register and remit monthly contributions under the "
            "National Pension Scheme Act."
        ),
        "document_type": "form",
        "category": "labour",
        "issuing_authority": "National Pension Scheme Authority (NAPSA)",
        "domains": ["napsa.co.zm"],
        "queries": [
            "NAPSA employer registration form PDF",
            "Zambia NAPSA employer registration form",
        ],
    },
    {
        "title": "NAPSA Member (Employee) Registration Form",
        "short_name": "NAPSA Member Form",
        "description": (
            "NAPSA member registration for individual employees. Generates the Social Security "
            "Number used for life-of-service contribution tracking."
        ),
        "document_type": "form",
        "category": "labour",
        "issuing_authority": "NAPSA",
        "domains": ["napsa.co.zm"],
        "queries": [
            "NAPSA member registration form PDF",
            "NAPSA employee registration form Zambia",
        ],
    },
    {
        "title": "Workers' Compensation Fund Control Board — Employer Registration",
        "short_name": "WCFCB Employer Registration",
        "description": (
            "Mandatory registration with the Workers' Compensation Fund Control Board "
            "(WCFCB) under the Workers' Compensation Act. Funds the scheme that compensates "
            "employees for workplace injury / death."
        ),
        "document_type": "form",
        "category": "labour",
        "issuing_authority": "WCFCB",
        "domains": ["wcfcb.co.zm"],
        "queries": [
            "WCFCB employer registration form Zambia PDF",
            "Workers Compensation Fund Control Board registration form",
        ],
    },

    # ─── Courts: civil-procedure forms, fee schedules ─────────────────────
    {
        "title": "High Court Civil Procedure Fee Schedule",
        "short_name": "High Court Fees",
        "description": (
            "Schedule of court fees for civil filings in the High Court of Zambia: "
            "originating processes, affidavits, search fees, certified copies."
        ),
        "document_type": "fee_schedule",
        "category": "court",
        "issuing_authority": "Judiciary of Zambia",
        "domains": ["judiciaryzambia.com"],
        "queries": [
            "High Court Zambia civil fees schedule PDF",
            "Zambia judiciary court fees PDF",
        ],
    },
    {
        "title": "High Court (Civil Procedure) Rules — Forms Schedule",
        "short_name": "High Court Forms",
        "description": (
            "Official forms attached to the High Court Rules: writ of summons, originating "
            "summons, originating notice of motion, affidavit, draft order, notice of "
            "appearance, etc."
        ),
        "document_type": "court_rule",
        "category": "court",
        "issuing_authority": "Judiciary of Zambia",
        "domains": ["judiciaryzambia.com", "zambialii.org"],
        "queries": [
            "High Court Rules Zambia forms schedule PDF",
            "Zambia High Court civil procedure forms PDF",
        ],
    },

    # ─── Other regulators ─────────────────────────────────────────────────
    {
        "title": "ZICTA ICT Licence Application Form",
        "short_name": "ZICTA Licence Form",
        "description": (
            "Application for a Class or Individual licence from the Zambia Information and "
            "Communications Technology Authority (ZICTA) — required to provide electronic "
            "communication services."
        ),
        "document_type": "application",
        "category": "ict",
        "issuing_authority": "ZICTA",
        "domains": ["zicta.zm"],
        "queries": [
            "ZICTA licence application form PDF",
            "Zambia ICT licence application form ZICTA",
        ],
    },
    {
        "title": "Bank of Zambia — Application for a Banking Licence",
        "short_name": "BoZ Banking Licence",
        "description": (
            "Application form and checklist for a banking licence under the Banking and "
            "Financial Services Act, 2017. Filed with the Bank of Zambia."
        ),
        "document_type": "application",
        "category": "financial",
        "issuing_authority": "Bank of Zambia",
        "domains": ["boz.zm"],
        "queries": [
            "Bank of Zambia banking licence application PDF",
            "BoZ licensing application Zambia PDF",
        ],
    },
]


# ── Tavily helpers (shared with the Acts scraper) ──────────────────────────


def tavily_search(query: str, *, include_domains: list[str] | None = None, max_results: int = 8) -> list[dict]:
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
    }
    if include_domains:
        payload["include_domains"] = include_domains
    try:
        r = httpx.post(
            "https://api.tavily.com/search",
            json=payload,
            timeout=30,
        )
        if r.status_code != 200:
            return []
        return (r.json() or {}).get("results", [])
    except Exception as e:  # noqa: BLE001
        print(f"    tavily error: {e}")
        return []


def pick_pdf_url(results: list[dict]) -> str | None:
    """Pick the first .pdf URL that looks like a Zambian form / gov doc."""
    candidates: list[tuple[int, str]] = []
    for r in results:
        url = (r.get("url") or "").strip()
        if not url:
            continue
        if not url.lower().endswith(".pdf"):
            continue
        # Score: gov domain > org > else
        score = 0
        if any(d in url for d in (".gov.zm", ".org.zm", ".co.zm", ".zm/")):
            score += 5
        if "form" in url.lower() or "application" in url.lower() or "registration" in url.lower():
            score += 2
        candidates.append((score, url))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def find_pdf_url(entry: dict) -> str | None:
    domains = entry.get("domains") or []
    for q in entry["queries"]:
        if domains:
            url = pick_pdf_url(tavily_search(q, include_domains=domains))
            if url:
                return url
        url = pick_pdf_url(tavily_search(q))
        if url:
            return url
    return None


# ── Storage upload (shared pattern with Acts scraper) ──────────────────────


def slugify(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return base or uuid.uuid4().hex


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


def patch_global_metadata(
    document_id: str,
    storage_path: str,
    page_count: int,
    size_bytes: int,
    canonical_url: str | None,
    category: str | None,
    issuing_authority: str | None,
    document_type: str,
) -> None:
    patch = {
        "is_global": True,
        "owner_id": None,
        "pdf_storage_path": storage_path,
        "pdf_page_count": page_count,
        "pdf_size_bytes": size_bytes,
        "document_type": document_type,
    }
    if canonical_url:
        patch["canonical_url"] = canonical_url
    get_db().table("legal_documents").update(patch).eq("id", document_id).execute()


def download(url: str) -> bytes | None:
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
    if not r.content or len(r.content) < 5_000:
        print(f"    suspiciously small ({len(r.content)} bytes); rejecting.")
        return None
    if not r.content.startswith(b"%PDF"):
        print(f"    not a PDF (magic bytes={r.content[:8]!r})")
        return None
    return r.content


def page_count_of(content: bytes) -> int:
    try:
        from pypdf import PdfReader
        return len(PdfReader(io.BytesIO(content)).pages)
    except Exception:
        return 0


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> int:
    results: list[dict] = []

    for i, entry in enumerate(FORMS, 1):
        title = entry["title"]
        print("\n" + "=" * 78)
        print(f"  [{i}/{len(FORMS)}] {title}")
        print("=" * 78)

        # Step 1 — discover PDF URL
        print("  Searching for canonical PDF…")
        url = find_pdf_url(entry)
        if not url:
            print("  ! could not find a PDF; skipping.")
            results.append({"title": title, "status": "no_url"})
            continue
        print(f"    found: {url}")

        # Step 2 — download
        print("  Downloading…")
        content = download(url)
        if content is None:
            results.append({"title": title, "status": "download_failed"})
            continue
        print(f"    {len(content):,} bytes")

        # Step 3 — save cache file (so we can re-ingest without re-downloading)
        slug = slugify(entry["short_name"] or title) + ".pdf"
        local = DOWNLOAD_DIR / slug
        local.write_bytes(content)
        print(f"    cached → {local}")

        # Step 4 — ingest
        try:
            ingestion = ingest_form_pdf(
                str(local),
                title=title,
                short_name=entry.get("short_name"),
                description=entry.get("description", ""),
                document_type=entry.get("document_type", "form"),
                category=entry.get("category"),
                issuing_authority=entry.get("issuing_authority"),
                source_url=url,
            )
        except Exception as e:  # noqa: BLE001
            print(f"  ! ingest error: {e}")
            results.append({"title": title, "status": "ingest_failed", "error": str(e)})
            continue

        if ingestion["status"] == "skipped":
            print("  · already in the library; skipping storage upload.")
            results.append({"title": title, "status": "skipped"})
            continue

        document_id = ingestion["document"]["id"]

        # Step 5 — upload PDF to Supabase storage and patch the row
        print("  Uploading PDF to Supabase storage…")
        try:
            storage_path = upload_pdf_to_storage(content, slug)
            patch_global_metadata(
                document_id,
                storage_path,
                page_count=page_count_of(content),
                size_bytes=len(content),
                canonical_url=url,
                category=entry.get("category"),
                issuing_authority=entry.get("issuing_authority"),
                document_type=entry.get("document_type", "form"),
            )
            print(f"    → {storage_path}")
        except Exception as e:  # noqa: BLE001
            print(f"  ! storage upload error: {e}")
            results.append({"title": title, "status": "storage_failed", "error": str(e)})
            continue

        results.append({
            "title": title,
            "status": "ok",
            "document_id": document_id,
            "chunks": ingestion.get("chunks_created"),
        })

        # Be polite to gov hosts; some throttle aggressively.
        time.sleep(1)

    # Summary
    print("\n\n" + "=" * 78)
    print("  SUMMARY")
    print("=" * 78)
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    for k, n in sorted(by_status.items()):
        print(f"  {k:18s} {n}")

    print("\n  Failed entries:")
    for r in results:
        if r["status"] != "ok" and r["status"] != "skipped":
            print(f"    - [{r['status']:16s}] {r['title']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
