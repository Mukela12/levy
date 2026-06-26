#!/usr/bin/env python3
"""Fix garbled OCR text in the corpus and RE-EMBED so retrieval matches clean
queries again. Many Act chunks lost their spaces at extraction
("Noticeforterminationofcontractofemployment"), which crippled both retrieval
and display. We re-space such runs offline with wordninja, then recompute the
OpenAI embedding on the cleaned text (no Anthropic credits).

Only long pure-alpha runs (>=19 chars) are touched, so real words and anything
with digits/punctuation are left alone.

  --doc <id>   process a single document (for testing)
  --all        process every global Act
"""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path
import wordninja

REPO = Path("/Users/mukelakatungu/levy/.claude/worktrees/gracious-mclean-3f2951")
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")
from app.db.supabase import get_db
from app.services.embedder import get_embeddings

db = get_db()
MASHED = re.compile(r"^[A-Za-z]{19,}$")  # a long pure-alpha run = garbled


def respace(text: str) -> tuple[str, bool]:
    if not text:
        return text, False
    changed = False
    out = []
    for tok in re.split(r"(\s+)", text):
        if MASHED.match(tok):
            sp = " ".join(wordninja.split(tok))
            if " " in sp:
                out.append(sp)
                changed = True
                continue
        out.append(tok)
    return "".join(out), changed


def process_doc(doc_id: str, label: str = "") -> int:
    chunks = (db.table("legal_chunks").select("id,content,metadata")
              .eq("document_id", doc_id).limit(6000).execute().data or [])
    changed = []
    for c in chunks:
        nc, c1 = respace(c.get("content") or "")
        meta = dict(c.get("metadata") or {})
        nst, c2 = respace(meta.get("section_title") or "")
        nan, c3 = respace(meta.get("act_name") or "")
        if c1 or c2 or c3:
            if c2:
                meta["section_title"] = nst
            if c3:
                meta["act_name"] = nan
            changed.append((c["id"], nc, meta))
    if not changed:
        return 0
    embs = get_embeddings([x[1] for x in changed])
    for (cid, nc, meta), emb in zip(changed, embs):
        db.table("legal_chunks").update(
            {"content": nc, "embedding": emb, "metadata": meta}
        ).eq("id", cid).execute()
    print(f"  {label or doc_id[:8]}: re-spaced + re-embedded {len(changed)}/{len(chunks)} chunks")
    return len(changed)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    if args.doc:
        process_doc(args.doc)
        return 0
    if args.all:
        acts = (db.table("legal_documents").select("id,short_name,title")
                .eq("document_type", "act").eq("is_global", True).execute().data or [])
        total = 0
        for a in acts:
            total += process_doc(a["id"], (a["short_name"] or a["title"])[:40])
        print(f"\nDONE: re-spaced + re-embedded {total} chunks across {len(acts)} global Acts")
        return 0
    print("pass --doc <id> or --all")
    return 1


if __name__ == "__main__":
    sys.exit(main())
