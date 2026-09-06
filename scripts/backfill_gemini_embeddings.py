#!/usr/bin/env python3
"""Fill legal_chunks.embedding_gemini so the second embedding space is real.

The corpus's primary embeddings are OpenAI text-embedding-3-small. This adds a
gemini-embedding-001 vector (768d) to every chunk, giving search a second,
independent vendor to stand on when the OpenAI account fails. The two spaces
never mix; this script writes ONLY the embedding_gemini column.

Free-tier aware: batches of 90 through batchEmbedContents, exponential backoff
on 429, resumable by construction (only chunks with a NULL gemini column are
fetched, so a stopped run just continues). Progress is by count, so run it in
the background and re-run at will.

Prerequisite: the 20260906000000_gemini_embedding_column.sql migration.

Usage:
  backend/.venv/bin/python scripts/backfill_gemini_embeddings.py --limit 5000
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")

from app.db.supabase import get_db                       # noqa: E402
from app.services.embedder import gemini_embed           # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100000, help="max chunks this run")
    ap.add_argument("--batch", type=int, default=90)
    args = ap.parse_args()
    db = get_db()

    total = (db.table("legal_chunks").select("id", count="exact")
             .is_("embedding_gemini", "null").limit(1).execute()).count or 0
    print(f"chunks missing a Gemini vector: {total:,}; doing up to {args.limit:,}", flush=True)

    done = failed = 0
    backoff = 5
    while done < args.limit:
        rows = (db.table("legal_chunks").select("id,content")
                .is_("embedding_gemini", "null")
                .limit(args.batch).execute().data) or []
        if not rows:
            print("nothing left to embed", flush=True)
            break
        texts = [(r.get("content") or " ")[:8000] for r in rows]
        try:
            embs = gemini_embed(texts, task="RETRIEVAL_DOCUMENT")
            backoff = 5
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                print(f"  rate limited; sleeping {backoff}s", flush=True)
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)
                continue
            print(f"  ! embed error: {msg[:100]}", flush=True)
            failed += 1
            if failed > 20:
                print("too many failures; stopping", flush=True)
                return 1
            time.sleep(10)
            continue
        for r, e in zip(rows, embs):
            db.table("legal_chunks").update({"embedding_gemini": e}).eq("id", r["id"]).execute()
        done += len(rows)
        if done % 900 < args.batch:
            print(f"  [{done:,}/{min(args.limit,total):,}]", flush=True)
        time.sleep(1.2)  # stay under free-tier RPM without measuring it

    left = (db.table("legal_chunks").select("id", count="exact")
            .is_("embedding_gemini", "null").limit(1).execute()).count or 0
    print(f"\nSUMMARY embedded={done:,} failed_batches={failed} remaining={left:,}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
