#!/usr/bin/env python3
"""Harvest the LONG TAIL of Zambian Acts toward full coverage.

We have ~184 major Acts. Zambia's statute book is ~450 principal Acts. This
script:
  1. Enumerates the full Act list (title + Chapter) from the server-rendered
     zambialaws.com consolidated-statutes index (robots-allowed; we use it
     only for the public *list of titles*, which are facts, not its text).
  2. Dedupes against what's already in the corpus.
  3. For each missing Act, reuses the proven pipeline from
     scrape_and_ingest_zambian_acts.py: Tavily-find the official PDF (prefer
     parliament.gov.zm / gov domains — public-domain statute text), download,
     validate, ingest (parse -> chunk -> OpenAI 768d embeddings), mark global.

Anthropic credits are untouched (embeddings are OpenAI; discovery is Tavily).
Idempotent + throttled. Run with --limit N.
"""
from __future__ import annotations
import argparse, re, sys, time, warnings
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

# Reuse the proven helpers from the existing curated harvester.
sys.path.insert(0, str(REPO / "scripts"))
import scrape_and_ingest_zambian_acts as base   # noqa: E402
from app.db.supabase import get_db               # noqa: E402
from app.services.ingester import ingest_pdf     # noqa: E402

INDEX = "https://www.zambialaws.com/consolidated-statutes/principal-legislation"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

STOP = {"act", "code", "of", "and", "the", "cap", "chapter", "a", "an", "to", "for", "in"}


def enumerate_acts() -> list[dict]:
    """Scrape every '<TITLE> ACT: CHAPTER <n>' entry across the paginated index."""
    acts: dict[str, dict] = {}
    with httpx.Client(timeout=30, headers=UA, verify=False, follow_redirects=True) as c:
        for start in range(0, 600, 50):
            try:
                r = c.get(INDEX, params={"limitstart": start, "limit": 50})
            except Exception:
                break
            if r.status_code != 200:
                break
            text = re.sub(r"<[^>]+>", " ", r.text)
            found = re.findall(r"([A-Z][A-Za-z0-9 &(),'’.\-/]{3,90}? ACT[A-Za-z0-9 (),'’.\-/]*?):\s*CHAPTER\s*(\d+)", text)
            new = 0
            for title, cap in found:
                title = re.sub(r"\s+", " ", title).strip()
                key = title.lower()
                if key not in acts:
                    acts[key] = {"title": title, "cap": cap}
                    new += 1
            if new == 0 and start > 0:
                break
            time.sleep(0.4)
    return list(acts.values())


def corpus_keywords() -> list[set]:
    rows = (get_db().table("legal_documents").select("title,short_name")
            .eq("document_type", "act").execute().data or [])
    out = []
    for r in rows:
        t = ((r.get("title") or "") + " " + (r.get("short_name") or "")).lower()
        out.append({w for w in re.findall(r"[a-z]{3,}", t) if w not in STOP})
    return out


def already_have(title: str, corpus: list[set]) -> bool:
    kw = {w for w in re.findall(r"[a-z]{3,}", title.lower()) if w not in STOP}
    if not kw:
        return False
    for c in corpus:
        if kw and len(kw & c) / len(kw) >= 0.8:   # 80% of the act's keywords already present
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40, help="max Acts to ingest this run")
    ap.add_argument("--list-only", action="store_true")
    args = ap.parse_args()

    all_acts = enumerate_acts()
    print(f"enumerated {len(all_acts)} Acts from the index")
    corpus = corpus_keywords()
    missing = [a for a in all_acts if not already_have(a["title"], corpus)]
    print(f"already have ~{len(all_acts)-len(missing)}; MISSING ~{len(missing)}")
    if args.list_only:
        for a in missing[:80]:
            print("  -", a["title"], f"(Cap {a['cap']})")
        return 0

    # Prefer the official source; exclude zambialii.org (robots/CC-NC — we do
    # not ingest its media, only cite it at query time).
    base.GOV_DOMAINS = ["parliament.gov.zm", "lawsofzambia.com", "moj.gov.zm",
                        "zambia.gov.zm", "pacra.org.zm"]

    ingested = failed = skipped = 0
    for a in missing:
        if ingested >= args.limit:
            break
        act = {"title": a["title"], "queries": [
            f"{a['title']} Zambia Act PDF",
            f"{a['title']} Cap {a['cap']} Zambia parliament PDF",
        ]}
        try:
            url = base.find_pdf_url(act)
        except Exception:
            url = None
        if url and "zambialii" in url.lower():
            url = None  # never ingest ZambiaLII-hosted files
        if not url:
            failed += 1
            continue
        content = base.download(url)
        if not content or not content.startswith(b"%PDF") or len(content) < 20_000:
            failed += 1
            continue
        if not base.looks_like_the_act(content, a["title"]):
            failed += 1
            continue
        # Reject consolidated volumes / compilations mis-matched to one Act
        # (a single principal Act is rarely >150 pages; a Laws-of-Zambia
        # volume is hundreds of pages and would pollute search + citations).
        try:
            from pypdf import PdfReader
            import io as _io
            if len(PdfReader(_io.BytesIO(content)).pages) > 150:
                failed += 1
                continue
        except Exception:
            pass
        if base.pdf_already_ingested(__import__("hashlib").sha256(content).hexdigest()):
            skipped += 1
            continue
        slug = base.slugify(a["title"]) + ".pdf"
        local = base.INPUT_DIR / slug if hasattr(base, "INPUT_DIR") else Path("/tmp") / slug
        try:
            local.write_bytes(content)
            res = ingest_pdf(str(local))
            if res.get("status") != "success":
                failed += 1; continue
            doc_id = res["document"]["id"]
            sp = base.upload_pdf_to_storage(content, slug)
            from pypdf import PdfReader
            import io
            pages = len(PdfReader(io.BytesIO(content)).pages)
            base.patch_global_metadata(doc_id, sp, pages, len(content), url)
            ingested += 1
            print(f"  [{ingested}/{args.limit}] {a['title'][:55]} (Cap {a['cap']})")
        except Exception as e:
            print(f"  ! {a['title'][:40]}: {str(e)[:60]}"); failed += 1
        time.sleep(0.5)

    print(f"\nSUMMARY ingested={ingested} skipped={skipped} failed={failed} missing_total={len(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
