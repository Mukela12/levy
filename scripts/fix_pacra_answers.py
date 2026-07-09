#!/usr/bin/env python3
"""Regenerate the three PACRA /answers pages that were grounded on the pre-session
MISLABELED forms (a journal saved as "PACRA Form 5", the annual report saved as
"PACRA Annual Return", etc.). Those answers told readers to file the wrong form.

Now that the mislabeled forms are unpublished and the correct forms exist
(Companies Form 3, Companies Form 1, BN Form III), regenerate the three answers
from the CLEAN corpus + the correct form names, and fix their sources. Re-runnable.
"""
import asyncio, json, os, sys
REPO = "/Users/mukelakatungu/levy/.claude/worktrees/gracious-mclean-3f2951"
sys.path.insert(0, REPO + "/backend"); sys.path.insert(0, REPO + "/scripts")
import _dns_resilient  # noqa
from dotenv import load_dotenv; load_dotenv(REPO + "/backend/.env")
import anthropic
from app.db.supabase import get_db
from app.services.tools import _search_corpus
from generate_answers import slugify

HAIKU = "claude-haiku-4-5-20251001"
ANS = REPO + "/frontend/src/data/answers.json"

# question -> (retrieval query, the correct downloadable forms to name, source list)
JOBS = {
    "How do I register a company with PACRA in Zambia?": (
        "incorporate a private company limited by shares Companies Act PACRA",
        "Levy holds the actual current forms: name clearance is PACRA Companies Form 1, "
        "incorporation is PACRA Companies Form 3, beneficial ownership is PACRA Companies Form 21, "
        "and the model articles are the PACRA Standard Articles of Association. Do NOT mention any "
        "'Form 5'. You may add that incorporation can also be done online on the PACRA portal "
        "(portal.pacra.org.zm).",
        [{"act": "Companies Act", "section": "12"},
         {"act": "PACRA Companies Form 3 (Application for Incorporation)", "section": ""},
         {"act": "PACRA Companies Form 1 (Name Clearance)", "section": ""}]),
    "How do I register a business name in Zambia?": (
        "register a business name Registration of Business Names Act PACRA",
        "The correct downloadable form Levy holds is PACRA BN Form III (Business Name Registration) "
        "under the Registration of Business Names Act No. 16 of 2011. Do NOT mention a generic "
        "'PACRA Business Name Form' or a fee schedule doc. You may add that a business name can also "
        "be registered online on the PACRA portal (portal.pacra.org.zm).",
        [{"act": "Registration of Business Names Act", "section": ""},
         {"act": "PACRA BN Form III (Business Name Registration)", "section": ""}]),
    "What are the annual return requirements for companies in Zambia?": (
        "company annual return filing requirements Companies Act",
        "Explain the annual return duty from the Companies Act. For HOW to file, say the annual "
        "return is filed on the PACRA portal (portal.pacra.org.zm); do NOT tell the reader to use a "
        "'PACRA Annual Return Form' or 'Form 5' (there is no such downloadable form).",
        [{"act": "Companies Act", "section": "184"},
         {"act": "Companies Act", "section": "185"}]),
}


async def main():
    force = "--force" in sys.argv
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    db = get_db()
    # map act-name -> document_id for the correct forms, to wire source links
    docs = {r["short_name"]: r["id"] for r in (db.table("legal_documents")
            .select("id,short_name").eq("is_global", True).limit(2000).execute().data or [])}
    a = json.load(open(ANS)); by_slug = {x["slug"]: x for x in a}
    done = 0
    for q, (rq, forms_note, srcs) in JOBS.items():
        slug = slugify(q)
        res = await _search_corpus(rq, top_k=10, threshold=0.2)
        chunks = res["result"].get("results") or res["result"].get("matches") or []
        context = "\n\n".join(f"[{c.get('act_name','?')}, S.{c.get('section','?')}] {c.get('content','')[:800]}"
                              for c in chunks[:8])
        prompt = (
            "You are Levy, a careful Zambian legal assistant. Using the excerpts below, write a "
            f"confident, practical answer for a general reader who asks: \"{q}\". Cite the governing "
            "Act inline in square brackets using the EXACT Act name shown, like [Companies Act, S.12]. "
            "Name the specific official form(s) the reader actually files. " + forms_note + " Do NOT "
            "invent form names or cite any form Levy does not hold. Be concise: 2 to 4 short "
            "paragraphs, plain English, no em dashes.\n\n"
            f"EXCERPTS:\n{context}"
        )
        msg = client.messages.create(model=HAIKU, max_tokens=950,
            messages=[{"role": "user", "content": prompt}])
        ans = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
        ans = ans.replace(" — ", ", ").replace("—", ", ")
        for s in srcs:
            s["document_id"] = docs.get(s["act"])
        entry = {"slug": slug, "category": "Business", "question": q, "answer": ans, "sources": srcs}
        if slug in by_slug: by_slug[slug].update(entry)
        else: a.append(entry); by_slug[slug] = entry
        done += 1
        print(f"  [{done}] {slug[:50]:50} ({len(ans)} chars)")
    json.dump(a, open(ANS, "w"), indent=2, ensure_ascii=False)
    # sanity: no deleted-form names remain in these answers
    bad = [x["slug"] for x in a if any(t in x.get("answer", "") for t in
           ("PACRA Form 5", "PACRA Annual Return Form", "PACRA Business Name Form")) or "—" in x.get("answer", "")]
    print(f"\nregenerated {done}; total {len(a)}; residual bad refs: {bad or 'NONE'}")


if __name__ == "__main__":
    asyncio.run(main())
