#!/usr/bin/env python3
"""Generate the e-Government /answers pages DIRECTLY from their curated civic
guides. The normal generate_answers.py path grounds via search_corpus, which
mis-matches acronym-heavy civic queries (TPIN/NRC/ZamPass surfaced the wrong
Act); grounding straight from the matching guide body guarantees correctness.

Reads the e-Government questions from generate_answers.QUESTIONS, maps each to
its guide (in ingest_civic_guides.GUIDES) via MAP, has Haiku write a practical
answer from the guide, and upserts the entry into answers.json. Re-runnable.
"""
import json, os, re, sys
REPO = "/Users/mukelakatungu/levy/.claude/worktrees/gracious-mclean-3f2951"
sys.path.insert(0, REPO + "/backend"); sys.path.insert(0, REPO + "/scripts")
import _dns_resilient  # noqa
from dotenv import load_dotenv; load_dotenv(REPO + "/backend/.env")
import anthropic
from app.db.supabase import get_db
from ingest_civic_guides import GUIDES
from generate_answers import QUESTIONS, slugify

HAIKU = "claude-haiku-4-5-20251001"
ANS = REPO + "/frontend/src/data/answers.json"

# slug fragment -> keyword that identifies the guide title
MAP = {
    "change-ownership-of-a-car": "transfer vehicle ownership",
    "get-a-tpin": "get a TPIN",
    "pay-road-tax": "pay road tax",
    "import-duty-on-a-car": "import duty is calculated",
    "driver-s-licence": "driver's licence",
    "apply-for-a-zambian-passport": "apply for a Zambian passport",
    "national-registration-card": "National Registration Card",
    "register-for-napsa": "How NAPSA works",
    "nhima-health-insurance": "How NHIMA",
    "zampass": "ZamPass, ZamPortal",
    "business-or-trading-licence": "business or trading licence from the council",
    "check-or-verify-a-land-title": "check or obtain a land title",
    # council/sector + civic-gap batch
    "fire-safety": "fire safety certificate",
    "health-permit": "health permit for a food business",
    "liquor-licence": "liquor licence",
    "sell-in-a-market": "market stall or street vending",
    "what-licence-does": "sector licence a business needs",
    "wcfcb": "WCFCB",
    "environmental-approval": "environmental approval or EIA",
    "with-the-zda": "register with the ZDA",
    "work-permit": "immigration permit or visa",
    "tax-clearance": "Tax Clearance Certificate",
    "property-transfer-tax": "Property Transfer Tax",
    "register-a-birth": "register a birth and get a birth certificate",
    "marriage-certificate": "get married and obtain a marriage certificate",
    "register-for-vat": "VAT registration works",
}


def guide_for(slug):
    for frag, kw in MAP.items():
        if frag in slug:
            for g in GUIDES:
                if kw.lower() in g["title"].lower():
                    return g
    return None


def main():
    db = get_db()
    guide_docs = {r["title"]: r["id"] for r in (db.table("legal_documents")
                  .select("id,title").eq("document_type", "guide").limit(500).execute().data or [])}
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    a = json.load(open(ANS))
    by_slug = {x["slug"]: x for x in a}
    egov = [(c, q) for c, q in QUESTIONS if c == "e-Government"]
    done = skipped = 0
    for cat, q in egov:
        slug = slugify(q)
        g = guide_for(slug)
        if not g:
            print("  ! no guide for", slug); skipped += 1; continue
        # skip if already generated from the correct guide (idempotent; pass --force to redo)
        cur = by_slug.get(slug)
        if cur and "--force" not in sys.argv and (cur.get("sources") or [{}])[0].get("act") == g["short_name"]:
            skipped += 1; continue
        prompt = (
            "You are Levy, a Zambian legal assistant. Using ONLY the official procedure guide "
            f"below, write a clear, practical answer for a general reader who asks: \"{q}\". Give "
            "the concrete steps and what to bring, name the responsible authority and the official "
            f"portal, and cite the governing law once in square brackets like [{g['law']}]. Where "
            "the guide flags a fee or figure as one to confirm, tell the reader to confirm the "
            "current amount on the official portal rather than stating a number as fixed. Be "
            "concise: 2 to 4 short paragraphs. Plain English. Do NOT use em dashes.\n\n"
            f"OFFICIAL GUIDE ({g['authority']}):\n{g['body']}"
        )
        msg = client.messages.create(model=HAIKU, max_tokens=900,
            messages=[{"role": "user", "content": prompt}])
        ans = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
        ans = ans.replace(" — ", ", ").replace("—", ", ")
        entry = {"slug": slug, "category": "e-Government", "question": q, "answer": ans,
                 "sources": [{"act": g["short_name"], "section": "",
                              "document_id": guide_docs.get(g["title"])}]}
        if slug in by_slug:
            by_slug[slug].update(entry)
        else:
            a.append(entry); by_slug[slug] = entry
        done += 1
        print(f"  [{done}] {slug[:46]:46} <- {g['short_name'][:32]}", flush=True)
    json.dump(a, open(ANS, "w"), indent=2, ensure_ascii=False)
    bad = [x["slug"] for x in a if "—" in x.get("answer", "")]
    print(f"\ngenerated {done} civic answers ({skipped} unmapped); total answers now {len(a)}; em-dashes: {bad or 'NONE'}")


if __name__ == "__main__":
    main()
