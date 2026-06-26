#!/usr/bin/env python3
"""QA: pull recent Levy conversations and surface what we can learn.

Read-only. Uses the backend service-role DB. Summarises:
  - volume (sessions/messages) over the last N days
  - each recent session: who, when, what they asked, did Levy answer
  - failure signals: empty assistant replies, the friendly-error sentence,
    tool errors, no-result searches
  - tool usage histogram (what users actually exercise)
"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
from datetime import datetime, timezone, timedelta

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")
from app.db.supabase import get_db

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 10
since = (datetime.now(timezone.utc) - timedelta(days=DAYS)).isoformat()
db = get_db()

ERR_SENTINEL = "temporary problem"

msgs = (db.table("chat_messages")
        .select("session_id,role,content,blocks,tool_calls,created_at")
        .gte("created_at", since)
        .order("created_at", desc=False)
        .limit(4000).execute().data or [])

# group by session
sess: dict[str, list[dict]] = {}
for m in msgs:
    sess.setdefault(m["session_id"], []).append(m)

# session meta
sids = list(sess.keys())
meta: dict[str, dict] = {}
for i in range(0, len(sids), 50):
    chunk = sids[i:i+50]
    rows = (db.table("chat_sessions").select("id,user_id,title,created_at")
            .in_("id", chunk).execute().data or [])
    for r in rows:
        meta[r["id"]] = r

tool_hist: dict[str, int] = {}
empty_replies = 0
error_replies = 0
tool_errors = 0
total_user = 0
total_asst = 0

def short(s, n=90):
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s[:n] + ("…" if len(s) > n else "")

# order sessions by latest activity
ordered = sorted(sess.items(), key=lambda kv: kv[1][-1]["created_at"], reverse=True)

print(f"==== RECENT CONVERSATIONS (last {DAYS}d) ====")
print(f"sessions touched: {len(ordered)}   messages: {len(msgs)}\n")

for sid, ms in ordered:
    m = meta.get(sid, {})
    uid = (m.get("user_id") or "anon")[:8]
    title = short(m.get("title") or "", 50)
    when = (ms[-1]["created_at"] or "")[:16].replace("T", " ")
    users = [x for x in ms if x["role"] == "user"]
    assts = [x for x in ms if x["role"] == "assistant"]
    total_user += len(users); total_asst += len(assts)
    # failure signals
    sess_flags = []
    for a in assts:
        c = a.get("content") or ""
        if not c.strip() and not a.get("blocks"):
            empty_replies += 1; sess_flags.append("EMPTY_REPLY")
        if ERR_SENTINEL in c.lower():
            error_replies += 1; sess_flags.append("ERROR_REPLY")
        for tc in (a.get("tool_calls") or []):
            name = tc.get("name") or "?"
            tool_hist[name] = tool_hist.get(name, 0) + 1
            if tc.get("status") == "error":
                tool_errors += 1; sess_flags.append(f"TOOLERR:{name}")
    flag = ("  ⚠ " + ",".join(sorted(set(sess_flags)))) if sess_flags else ""
    print(f"[{when}] u={uid} ({len(users)}q/{len(assts)}a) {title}{flag}")
    for u in users[:4]:
        print(f"      Q: {short(u.get('content'))}")
    if len(users) > 4:
        print(f"      … +{len(users)-4} more")

print("\n==== SIGNALS ====")
print(f"user msgs={total_user}  assistant msgs={total_asst}")
print(f"empty replies={empty_replies}  error-sentence replies={error_replies}  tool errors={tool_errors}")
print("\ntool usage:")
for name, n in sorted(tool_hist.items(), key=lambda kv: -kv[1]):
    print(f"   {n:4d}  {name}")
