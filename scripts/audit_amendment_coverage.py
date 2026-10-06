#!/usr/bin/env python3
"""How much of the amendment record behind each held Act does Levy actually have?

The section map can only warn about a dead section if the Act that killed it
is in the library and was read. The 28 Sep 2026 benchmark caught Levy applying
section 24 of the Immigration and Deportation Act 2010, repealed in 2016,
because nothing had read the 2016 amending Act. This audit measures that
coverage instead of waiting for the next benchmark to find a hole:

  1. MISSING   amendment Acts on Parliament's index whose principal Act is in
               the library but which are not in the library themselves.
  2. UNREAD    amendment Acts that are in the library but from which the
               section map read no section-level change.
  3. READ      amendment Acts whose changes reached the section map.

Matching is by Act number and year ("No. 19 of 2016"), because the library's
titles for amendment Acts often lose the year and would collide across years.

    python scripts/audit_amendment_coverage.py               # crawls the index (~2 min)
    python scripts/audit_amendment_coverage.py --index FILE  # reuse a saved crawl

Read-only. Writes scripts/amendment_coverage.json for the next run to diff.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import types
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))
from app.db.supabase import get_db  # noqa: E402

_spec = importlib.util.spec_from_file_location("harvest", REPO / "scripts" / "harvest_parliament_acts.py")
harvest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harvest)

LAW_MAP = REPO / "backend" / "app" / "data" / "law_map.json"
SECTION_MAP = REPO / "backend" / "app" / "data" / "section_map.json"
OUT = REPO / "scripts" / "amendment_coverage.json"
AMEND = re.compile(r"\(\s*amendment(?:\s+act)?\s*\)", re.I)
NUMBER = re.compile(r"No\.?\s*(\d+)\s*of\s*((?:19|20)\d{2})", re.I)


def stem_key(title: str) -> str:
    """'The Immigration and Deportation (Amendment) Act, 2016' -> 'immigration deportation'."""
    base = AMEND.split(title)[0]
    base = re.sub(r"\b(?:19|20)\d{2}\b", " ", base)
    return harvest.norm(base)


def number_of(*texts: str) -> tuple[int, int] | None:
    for t in texts:
        m = NUMBER.search(t or "")
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def library(db) -> list[dict]:
    out, i = [], 0
    while True:
        rows = (db.table("legal_documents").select("id,title,short_name,act_number,year,document_type")
                .eq("document_type", "act").range(i, i + 999).execute().data or [])
        out += rows
        if len(rows) < 1000:
            return out
        i += 1000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="", help="a saved crawl (JSON list) instead of crawling")
    ap.add_argument("--save-index", default="", help="write the crawl here for reuse")
    args = ap.parse_args()

    if args.index and Path(args.index).exists():
        index = json.loads(Path(args.index).read_text())
    else:
        print("crawling Parliament's Acts index ...", flush=True)
        index = harvest.crawl_index(harvest.http())
        if args.save_index:
            Path(args.save_index).write_text(json.dumps(index))
    entries = [harvest.parse_entry(e) for e in index]

    lm = json.loads(LAW_MAP.read_text())["documents"]
    sm = json.loads(SECTION_MAP.read_text())
    read_ids = {h["by_id"] for p in sm["principals"].values()
                for bucket in (p["sections"], p["parts"]) for s in bucket.values() for h in s["history"]}

    docs = library(get_db())
    principals: dict[str, list[dict]] = defaultdict(list)
    held_numbers: dict[tuple[int, int], dict] = {}
    # Some held amendment Acts carry no Act number ("The Landlord and Tenant
    # (Business Premises) (Amendment Act), 2020"), so name and year match too.
    held_by_name: dict[tuple[str, int], dict] = {}
    for d in docs:
        title = d.get("title") or ""
        n = number_of(d.get("act_number") or "", title, d.get("short_name") or "")
        if n:
            held_numbers.setdefault(n, d)
        if AMEND.search(title):
            y = d.get("year") or (int(m.group(0)) if (m := re.search(r"\b(?:19|20)\d{2}\b", title)) else None)
            if y:
                held_by_name.setdefault((stem_key(title), int(y)), d)
        else:
            principals[stem_key(title)].append(d)

    rows = []
    for e in entries:
        if not e["amendment"]:
            continue
        key = stem_key(e["title"])
        held_principal = principals.get(key)
        if not held_principal:
            continue    # the Act it amends is not in the library either
        n = number_of(e.get("act_number") or "", e.get("no") or "", e["title"])
        doc = held_numbers.get(n) if n else None
        if doc and not AMEND.search(doc.get("title") or ""):
            doc = None  # a principal that happens to share the number is not this amendment
        if not doc and e.get("year"):
            doc = held_by_name.get((key, int(e["year"])))
        state = "MISSING" if not doc else ("READ" if doc["id"] in read_ids else "UNREAD")
        live = [p for p in held_principal if (lm.get(p["id"]) or {}).get("status") not in ("repealed",)]
        rows.append({"state": state, "title": e["title"], "number": e.get("act_number") or "",
                     "year": e.get("year"), "node": e["node"], "principal": (live or held_principal)[0]["title"],
                     "principal_repealed": not live, "doc_id": doc["id"] if doc else None})

    by_state = defaultdict(list)
    for r in rows:
        by_state[r["state"]].append(r)
    print(f"\namendment Acts on Parliament's index whose principal Act is held: {len(rows)}")
    for s in ("READ", "UNREAD", "MISSING"):
        print(f"  {s:<8} {len(by_state[s])}")

    missing = [r for r in by_state["MISSING"] if not r["principal_repealed"]]
    print(f"\nMISSING, principal in force ({len(missing)}), most recent first:")
    by_principal = defaultdict(list)
    for r in missing:
        by_principal[r["principal"]].append(r)
    for principal, rs in sorted(by_principal.items(), key=lambda kv: -max(r["year"] or 0 for r in kv[1])):
        years = ", ".join(f"{r['number'] or r['year']}" for r in sorted(rs, key=lambda r: -(r["year"] or 0)))
        print(f"  {principal[:58]:<60} {len(rs)}: {years}")
    print(f"\nUNREAD ({len(by_state['UNREAD'])}): held, but no section-level change was read")
    for r in sorted(by_state["UNREAD"], key=lambda r: -(r["year"] or 0))[:40]:
        print(f"  {r['title'][:70]:<72} {r['number']}")

    previous = json.loads(OUT.read_text()) if OUT.exists() else None
    OUT.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "rows": rows}, indent=1))
    if previous:
        before = {r["node"]: r["state"] for r in previous.get("rows", [])}
        changed = [(r["title"], before.get(r["node"]), r["state"]) for r in rows if before.get(r["node"]) != r["state"]]
        print(f"\nchanged since {previous.get('generated_at')}: {len(changed)}")
        for t, a, b in changed[:20]:
            print(f"  {t[:60]:<62} {a} -> {b}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
