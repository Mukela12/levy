"""Review Levy's shared memory of legal updates (backend/app/services/legal_updates.py).

Answers and the watcher record official-source facts as "verified" once the
server finds the quoted words on the page. A person's approval is what lets a
rate change reach a calculator (an approved "paye-bands-2027" row sets the 2027
PAYE bands), and a rejection hides a wrong one from every answer at once.

  backend/.venv/bin/python scripts/legal_updates.py list [--status verified|pending|approved|all]
  backend/.venv/bin/python scripts/legal_updates.py show ID
  backend/.venv/bin/python scripts/legal_updates.py approve ID [--note TEXT]
  backend/.venv/bin/python scripts/legal_updates.py reject ID --note TEXT
  backend/.venv/bin/python scripts/legal_updates.py recheck      # re-fetch pending rows' pages
  backend/.venv/bin/python scripts/legal_updates.py watch        # run the official-source watcher once
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.db.supabase import get_db  # noqa: E402
from app.services import legal_updates  # noqa: E402


def _rows(status: str) -> list[dict]:
    q = get_db().table("legal_updates").select("*").order("first_seen_at", desc=True).limit(200)
    if status != "all":
        q = q.eq("status", status)
    return q.execute().data or []


def _line(r: dict) -> str:
    eff = f" eff {r['effective_date']}" if r.get("effective_date") else ""
    return (f"{r['id'][:8]}  {r['status']:<9} {r['kind']:<12} seen {r.get('seen_count', 1):>2}x{eff}\n"
            f"          {r['statement']}\n          {r['source_url']}")


async def _recheck() -> None:
    for r in _rows("pending"):
        status, digest = await legal_updates.confirm(r["source_url"], r["source_quote"])
        if status == "verified":
            get_db().table("legal_updates").update({"status": "verified", "source_hash": digest}).eq("id", r["id"]).execute()
        print(f"{r['id'][:8]}  {status}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--status", default="verified", choices=["verified", "pending", "approved", "rejected", "superseded", "all"])
    sh = sub.add_parser("show")
    sh.add_argument("id")
    for name in ("approve", "reject", "supersede"):
        p = sub.add_parser(name)
        p.add_argument("id")
        p.add_argument("--note", default=None)
    sub.add_parser("recheck")
    sub.add_parser("watch")
    args = ap.parse_args()

    if args.cmd == "list":
        rows = _rows(args.status)
        print("\n".join(_line(r) for r in rows) or "(none)")
    elif args.cmd in ("show", "approve", "reject", "supersede"):
        rows = [r for r in _rows("all") if r["id"].startswith(args.id)]
        if len(rows) != 1:
            sys.exit(f"{len(rows)} updates match {args.id!r}; give more of the id")
        row = rows[0]
        if args.cmd == "show":
            print(json.dumps(row, indent=1, default=str))
            return
        if args.cmd == "reject" and not args.note:
            sys.exit("say why with --note")
        status = {"approve": "approved", "reject": "rejected", "supersede": "superseded"}[args.cmd]
        print(_line(legal_updates.review(row["id"], status, args.note)))
    elif args.cmd == "recheck":
        asyncio.run(_recheck())
    elif args.cmd == "watch":
        from app.services import watcher
        print(json.dumps(asyncio.run(watcher.run_once()), indent=1, default=str))


if __name__ == "__main__":
    main()
