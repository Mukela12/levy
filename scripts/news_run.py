#!/usr/bin/env python3
"""Run Levy News once (shadow mode): feeds, stories, checks.

  backend/.venv/bin/python scripts/news_run.py --dry-run --out DIR [--max-checks 3] [--budget 0.50]
  backend/.venv/bin/python scripts/news_run.py [--max-checks 5] [--budget 1.00]

--dry-run keeps everything in memory and writes DIR/run.json instead of the
news_* tables, so it works before the migration has been applied. Model calls
are real either way and cost about $0.07 a check.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=str(REPO.parent / "levy-research" / "news-pilot" / "shadow"))
    ap.add_argument("--max-checks", type=int, default=3)
    ap.add_argument("--budget", type=float, default=0.5)
    ap.add_argument("--since-hours", type=float, default=36)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in ("httpx", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    from app.services.news import pipeline
    from app.services.news.store import MemoryStore, SupabaseStore
    store = MemoryStore() if args.dry_run else SupabaseStore()
    result = pipeline.run_once(store=store, max_checks=args.max_checks, budget_usd=args.budget, since_hours=args.since_hours)
    print(json.dumps(result, indent=1))
    if args.dry_run:
        path = Path(args.out) / "run.json"
        store.dump(path)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
