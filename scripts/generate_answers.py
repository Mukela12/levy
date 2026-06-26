#!/usr/bin/env python3
"""Pre-generate concise, corpus-grounded answers to high-intent Zambian-law
questions, for the public /answers/[slug] SEO pages.

Cheap + one-time: for each question we run one corpus vector search and one
Haiku synthesis (no full agent loop), so the whole batch costs ~$1. Output is
a static JSON the frontend renders as server-rendered pages. The pages also let
the reader continue in the live chat, so the static answer is just the door in.
"""
from __future__ import annotations
import asyncio, json, re, sys
from pathlib import Path

REPO = Path("/Users/mukelakatungu/levy/.claude/worktrees/gracious-mclean-3f2951")
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")
from app.config import get_settings
from app.services.tools import _search_corpus
import anthropic

OUT = REPO / "frontend" / "src" / "data" / "answers.json"
HAIKU = "claude-haiku-4-5-20251001"

# High-intent questions people actually search, mapped to the corpus.
QUESTIONS: list[tuple[str, str]] = [
    ("Employment", "What is the minimum notice period for terminating employment in Zambia?"),
    ("Employment", "How is severance pay calculated in Zambia?"),
    ("Employment", "What are an employee's rights when dismissed in Zambia?"),
    ("Employment", "What is the maternity leave entitlement in Zambia?"),
    ("Employment", "How is gratuity calculated for employees in Zambia?"),
    ("Employment", "What is constructive dismissal under Zambian law?"),
    ("Employment", "What are the rules on redundancy and redundancy pay in Zambia?"),
    ("Employment", "How much annual leave is an employee entitled to in Zambia?"),
    ("Business", "How do I register a company with PACRA in Zambia?"),
    ("Business", "What is the difference between a limited company and a registered business name in Zambia?"),
    ("Business", "What are the annual return requirements for companies in Zambia?"),
    ("Business", "What are the duties of a company director in Zambia?"),
    ("Land", "How do I transfer land or title to property in Zambia?"),
    ("Land", "What is property transfer tax in Zambia and who pays it?"),
    ("Land", "What consent is required to assign land in Zambia?"),
    ("Land", "What are a tenant's rights and the notice to end a tenancy in Zambia?"),
    ("Family", "What are the grounds for divorce in Zambia?"),
    ("Family", "How is child maintenance determined in Zambia?"),
    ("Family", "How does intestate succession work in Zambia when someone dies without a will?"),
    ("Family", "What are the requirements for a valid will in Zambia?"),
    ("Rights", "What are my rights when I am arrested in Zambia?"),
    ("Rights", "How does bail work in Zambia?"),
    ("Rights", "What fundamental rights does the Constitution of Zambia protect?"),
    ("Intellectual Property", "How do I register a trademark in Zambia?"),
    ("Intellectual Property", "How do I register a patent in Zambia?"),
    ("Contract", "What are the requirements for a valid contract in Zambia?"),
    ("Business", "What incentives are available for foreign investors in Zambia?"),
    ("Study", "What subjects (heads) are examined in the ZIALE bar exam?"),
    ("Study", "What is the pass mark and structure of the ZIALE LPQE exam?"),
    ("Employment", "What is the difference between summary dismissal and dismissal with notice in Zambia?"),
]


def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:70]


def retrieval_query(q: str) -> str:
    """Strip question framing so retrieval matches the core legal terms, not
    'what is the ... in zambia'. The Haiku step still answers the full question."""
    t = q.lower().strip().rstrip("?")
    for p in ("what is the difference between", "what is the", "what are the",
              "what are", "what is", "how do i", "how is", "how does",
              "how much is", "how much", "what fundamental"):
        if t.startswith(p):
            t = t[len(p):]
            break
    t = t.replace(" in zambia", "").replace(" under zambian law", "").strip()
    return t or q


async def main() -> int:
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    out = []
    for cat, q in QUESTIONS:
        res = await _search_corpus(retrieval_query(q), top_k=10, threshold=0.2)
        chunks = res["result"].get("results") or res["result"].get("matches") or []
        if not chunks:
            print(f"  SKIP (no corpus grounding): {q}")
            continue
        context = "\n\n".join(
            f"[{c.get('act_name','?')}, S.{c.get('section','?')}] {c.get('content','')[:850]}"
            for c in chunks[:8]
        )
        prompt = (
            "You are Levy, a careful Zambian legal assistant. Using the statute excerpts "
            "below, write a confident, self-contained answer for a general reader. Be "
            "concise (2 to 4 short paragraphs), accurate and practical. Cite the provision "
            "inline in square brackets using the EXACT Act name shown in the excerpt, like "
            "[Employment Code Act, S.53], whenever you state a rule. If more than one Act is "
            "relevant, rely on the most recent and most complete provision (for example the "
            "Employment Code Act of 2019 rather than the older Employment Act). Do NOT "
            "comment on the excerpts themselves or say they are incomplete or limited; just "
            "answer from what the law provides. Plain English. Do not use em dashes.\n\n"
            f"QUESTION: {q}\n\nEXCERPTS:\n{context}"
        )
        msg = client.messages.create(
            model=HAIKU, max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
        # dedupe sources by (act, section)
        seen, sources = set(), []
        for c in chunks:
            key = (c.get("act_name"), c.get("section"))
            if key in seen or not c.get("act_name"):
                continue
            seen.add(key)
            sources.append({
                "act": c.get("act_name"),
                "section": str(c.get("section") or ""),
                "document_id": c.get("document_id"),
            })
            if len(sources) >= 4:
                break
        out.append({"slug": slugify(q), "category": cat, "question": q, "answer": answer, "sources": sources})
        print(f"  OK [{cat}] {q[:55]} ({len(sources)} sources, {len(answer)} chars)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nWROTE {len(out)} answers -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
