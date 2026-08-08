#!/usr/bin/env python3
"""Read the answer-feedback signal, sliced by the model that produced it.

This is how the Haiku-vs-Sonnet question gets settled with data instead of a
4-case benchmark. Run it whenever you want a read:

    python scripts/watch_feedback.py [days]

It reports, per model: how many answers were rated, the thumbs-up rate, and
every thumbs-down reason in full — the reasons are worth more than the counts,
because they say WHAT was wrong.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
import _dns_resilient  # noqa: F401  (flaky local DNS; must import first)
from dotenv import load_dotenv

load_dotenv(REPO / "backend" / ".env")
from app.db.supabase import get_db

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 14
since = (datetime.now(timezone.utc) - timedelta(days=DAYS)).isoformat()
db = get_db()

fb = (db.table("message_feedback")
      .select("message_id,rating,reason,created_at")
      .gte("created_at", since).order("created_at").execute().data or [])

print(f"\nANSWER FEEDBACK — last {DAYS} days")
print("=" * 68)
if not fb:
    print("  No votes yet. The control ships with the answer, so this fills as\n"
          "  people use Levy — give it a few days of real traffic.")
else:
    # Attribute each vote to the model that actually produced the answer.
    ids = [f["message_id"] for f in fb]
    models: dict[str, str] = {}
    for i in range(0, len(ids), 50):
        rows = (db.table("chat_messages").select("id,model")
                .in_("id", ids[i:i + 50]).execute().data or [])
        for r in rows:
            models[r["id"]] = r.get("model") or "(unrecorded)"

    by_model: dict[str, list[dict]] = defaultdict(list)
    for f in fb:
        by_model[models.get(f["message_id"], "(unrecorded)")].append(f)

    print(f"  {len(fb)} vote(s) across {len(by_model)} model(s)\n")
    print(f"  {'model':26} {'votes':>6} {'up':>5} {'down':>5} {'up-rate':>9}")
    print("  " + "-" * 56)
    for model, votes in sorted(by_model.items(), key=lambda kv: -len(kv[1])):
        up = sum(1 for v in votes if v["rating"] == "up")
        down = len(votes) - up
        rate = f"{100 * up / len(votes):.0f}%" if votes else "-"
        print(f"  {model:26} {len(votes):>6} {up:>5} {down:>5} {rate:>9}")

    reasons = [(models.get(f["message_id"], "?"), f["reason"], f["created_at"][:10])
               for f in fb if f["rating"] == "down" and (f.get("reason") or "").strip()]
    if reasons:
        print(f"\n  WHY people voted down ({len(reasons)} with a reason):")
        for model, reason, day in reasons:
            print(f"    [{day}] {model}")
            print(f"      {reason.strip()[:400]}")
    else:
        down_total = sum(1 for f in fb if f["rating"] == "down")
        if down_total:
            print(f"\n  {down_total} thumbs-down, none with a written reason.")

# The anonymous funnel — the other thing that was previously unmeasurable.
ev = (db.table("anon_events").select("outcome,trial_number,had_sources,duration_ms,visitor_hash")
      .gte("created_at", since).execute().data or [])
print(f"\n\nANONYMOUS FUNNEL — last {DAYS} days")
print("=" * 68)
if not ev:
    print("  No anonymous events recorded yet.")
else:
    counts: dict[str, int] = defaultdict(int)
    for e in ev:
        counts[e["outcome"]] += 1
    visitors = len({e["visitor_hash"] for e in ev if e.get("visitor_hash")})
    asked = counts.get("asked", 0)
    answered = counts.get("answered", 0)
    print(f"  {visitors} distinct visitor-days, {len(ev)} events\n")
    for outcome, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"    {outcome:20} {n:>5}")
    if asked:
        print(f"\n  {100 * answered / asked:.0f}% of started questions produced an answer")
        grounded = sum(1 for e in ev if e.get("had_sources"))
        print(f"  {grounded} of {answered} answers cited the corpus")
        depth: dict[int, int] = defaultdict(int)
        for e in ev:
            if e["outcome"] == "asked" and e.get("trial_number"):
                depth[e["trial_number"]] += 1
        if depth:
            run = "  ".join(f"Q{k}:{v}" for k, v in sorted(depth.items()))
            print(f"  How far into the free trial people get:  {run}")
print()
