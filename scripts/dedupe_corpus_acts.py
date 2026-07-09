#!/usr/bin/env python3
"""De-duplicate superseded / duplicate Acts in the global corpus so retrieval
prefers current, cleaner law. Reversible: we set is_global=false (unpublish),
never delete. Conservative: we only act on two clear cases and leave anything
legally ambiguous for human review.

  1. EXACT duplicates: two rows whose normalized title is identical (e.g.
     "INSURANCE ACT" vs "REPUBLIC OF ZAMBIA THE INSURANCE ACT"). Keep the
     cleaner-text version (then more chunks); unpublish the other.
  2. KNOWN supersessions: a small, confident hardcoded list (the repealed
     Employment Act, superseded by the Employment Code Act 2019).

Run with --apply to commit; default is a dry run.
"""
from __future__ import annotations
import argparse, re, sys
from collections import defaultdict
from pathlib import Path

REPO = Path("/Users/mukelakatungu/levy/.claude/worktrees/gracious-mclean-3f2951")
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")
from app.db.supabase import get_db

db = get_db()

# Confident supersessions: normalized_title -> reason. The loser is unpublished
# (kept reversible). Only add entries you are certain about.
SUPERSEDED = {
    "employment act": "repealed and replaced by the Employment Code Act, No. 3 of 2019",
}


def norm(title: str, short: str | None) -> str:
    t = (short or title or "")
    t = re.sub(r"^republic of zambia\s+", "", t, flags=re.I)
    t = re.sub(r"^the\s+", "", t, flags=re.I)
    t = re.sub(r"\bchapter\b.*$", "", t, flags=re.I)
    t = re.sub(r"[^a-z ]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def text_quality(doc_id: str) -> float:
    """Higher is cleaner. Fraction of word-tokens that are NOT mashed runs."""
    rows = db.table("legal_chunks").select("content").eq("document_id", doc_id).limit(12).execute().data or []
    toks, bad = 0, 0
    for r in rows:
        for w in re.findall(r"\S+", r.get("content") or ""):
            toks += 1
            if len(w) > 18:
                bad += 1
    return 1.0 - (bad / toks) if toks else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    rows = (db.table("legal_documents")
            .select("id,title,short_name,year,total_chunks")
            .eq("document_type", "act").eq("is_global", True).execute().data or [])
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[norm(r["title"], r.get("short_name"))].append(r)

    to_unpublish: list[tuple[dict, str]] = []

    # 1) exact-normalized duplicates
    for key, versions in groups.items():
        if len(versions) < 2:
            continue
        scored = sorted(
            versions,
            key=lambda v: (text_quality(v["id"]), v.get("total_chunks") or 0),
            reverse=True,
        )
        keep, losers = scored[0], scored[1:]
        for lo in losers:
            to_unpublish.append((lo, f"duplicate of kept '{keep['short_name'] or keep['title']}' (id {keep['id'][:8]})"))

    # 2) known supersessions
    for key, versions in groups.items():
        if key in SUPERSEDED:
            for v in versions:
                if not any(v["id"] == u[0]["id"] for u in to_unpublish):
                    to_unpublish.append((v, SUPERSEDED[key]))

    print(f"{len(rows)} global acts. Proposing to unpublish {len(to_unpublish)}:\n")
    for v, reason in to_unpublish:
        q = text_quality(v["id"])
        print(f"  - {(v['short_name'] or v['title'])[:50]:50}  {v.get('total_chunks') or 0:>4}ch  q={q:.2f}")
        print(f"      reason: {reason}")

    if not args.apply:
        print("\n(dry run; re-run with --apply to commit)")
        return 0

    for v, reason in to_unpublish:
        db.table("legal_documents").update({"is_global": False}).eq("id", v["id"]).execute()
    print(f"\nAPPLIED: unpublished {len(to_unpublish)} acts (is_global=false, reversible).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
