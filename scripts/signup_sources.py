"""Which channel brought Levy's signups and guest questions.

The browser keeps a visit's UTM tags and referring domain (frontend
lib/attribution.ts) and saves them with a new account as user metadata
`signup_source` ({first, last}); anonymous questions carry the same summary in
anon_events.meta.source. Signups before 12 Oct 2026 have no source.

  backend/.venv/bin/python scripts/signup_sources.py                  # last 30 days
  backend/.venv/bin/python scripts/signup_sources.py --since 2026-10-12

Analytics accounts are left out, as in every Levy report. Tag links as
?utm_source=linkedin&utm_medium=post&utm_campaign=final-pay.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.db.supabase import get_db  # noqa: E402

EXCLUDED = ("0bb36a24", "c391a7a2", "e49f9bea", "e1b20d71", "ffcdfb84")


def channel(touch: dict | None) -> str:
    if not isinstance(touch, dict) or not touch:
        return "no source (before tracking)"
    if touch.get("utm_source") or touch.get("utm_campaign"):
        bits = [touch.get("utm_source") or "?", touch.get("utm_medium"), touch.get("utm_campaign")]
        return " / ".join(b for b in bits if b)
    if touch.get("ref_host"):
        return f"referred by {touch['ref_host']}"
    return "direct"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", default=(dt.date.today() - dt.timedelta(days=30)).isoformat())
    args = ap.parse_args()
    db = get_db()

    users, page = [], 1
    while True:
        res = db.auth.admin.list_users(page=page, per_page=1000)
        batch = res if isinstance(res, list) else getattr(res, "users", [])
        users += batch
        if len(batch) < 1000:
            break
        page += 1
    new = [u for u in users if str(u.created_at)[:10] >= args.since
           and not str(u.id).startswith(EXCLUDED) and "qa-probe" not in (u.email or "")]
    first, last = collections.Counter(), collections.Counter()
    for u in new:
        source = (u.user_metadata or {}).get("signup_source") or {}
        first[channel(source.get("first"))] += 1
        last[channel(source.get("last") or source.get("first"))] += 1

    guests = collections.Counter()
    rows = (db.table("anon_events").select("meta").eq("outcome", "asked").gte("created_at", args.since)
            .limit(20000).execute().data) or []
    for r in rows:
        guests[channel(((r.get("meta") or {}).get("source")))] += 1

    print(f"Since {args.since}: {len(new)} signups, {sum(guests.values())} guest questions\n")
    print("Signups by first visit's source:")
    for name, n in first.most_common():
        print(f"  {n:>4}  {name}")
    print("\nSignups by latest tagged visit before signup:")
    for name, n in last.most_common():
        print(f"  {n:>4}  {name}")
    print("\nGuest questions by source:")
    for name, n in guests.most_common():
        print(f"  {n:>4}  {name}")


if __name__ == "__main__":
    main()
