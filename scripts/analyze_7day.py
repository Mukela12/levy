#!/usr/bin/env python3
"""7-day Levy analysis: real-user activity, failures, tool usage, and the
specific issues/opportunities visible in saved conversations. Read-only."""
from __future__ import annotations
import sys, re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter

REPO = Path("/Users/mukelakatungu/levy/.claude/worktrees/gracious-mclean-3f2951")
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv; load_dotenv(REPO / "backend" / ".env")
from app.db.supabase import get_db

DAYS = 7
since = (datetime.now(timezone.utc) - timedelta(days=DAYS)).isoformat()
db = get_db()

msgs = (db.table("chat_messages")
        .select("session_id,role,content,blocks,tool_calls,created_at")
        .gte("created_at", since).order("created_at").limit(5000).execute().data or [])

sess = defaultdict(list)
for m in msgs:
    sess[m["session_id"]].append(m)

# session meta (user, title)
ids = list(sess.keys())
meta = {}
for i in range(0, len(ids), 50):
    for r in (db.table("chat_sessions").select("id,user_id,title,created_at")
              .in_("id", ids[i:i+50]).execute().data or []):
        meta[r["id"]] = r

def short(s, n=70):
    return re.sub(r"\s+", " ", (s or "").strip())[:n]

ERR_MARKERS = ["encountered an error", "temporary problem", "please sign in", "try again",
               "stuck in a loop", "i apologize", "let me draft", "i can't see", "lost"]

# ---- daily activity ----
daily = defaultdict(lambda: {"sess": set(), "u": 0, "a": 0, "err": 0})
tool_hist = Counter()
study = drafting = quiz = websearch = 0
errors = []          # (date, uid, query, kind)
retries = []         # (uid, query, count)
topics = Counter()
all_queries = []

for sid, ms in sess.items():
    m = meta.get(sid, {})
    uid = (m.get("user_id") or "ANON")[:8]
    qcount = Counter()
    for x in ms:
        d = (x["created_at"] or "")[:10]
        daily[d]["sess"].add(sid)
        if x["role"] == "user":
            daily[d]["u"] += 1
            q = short(x.get("content"), 120)
            all_queries.append(q)
            qcount[q.lower()] += 1
        else:
            daily[d]["a"] += 1
            c = (x.get("content") or "").lower()
            if (not c.strip() and not x.get("blocks")):
                daily[d]["err"] += 1; errors.append((d, uid, "<empty reply>", "empty"))
            elif any(k in c for k in ["encountered an error", "temporary problem", "please sign in"]):
                daily[d]["err"] += 1
                kind = "signin-block" if "please sign in" in c else "error"
                errors.append((d, uid, short(x.get("content"), 60), kind))
            for tc in (x.get("tool_calls") or []):
                n = tc.get("name") or "?"; tool_hist[n] += 1
                if n in ("make_cheat_sheet",): study += 1
                if n == "generate_quiz": quiz += 1
                if n and "draft" in n: drafting += 1
                if n in ("web_search", "gov_search", "news_search"): websearch += 1
    for q, c in qcount.items():
        if c >= 2 and len(q) > 8:
            retries.append((uid, q[:60], c))

print(f"==== LEVY {DAYS}-DAY ANALYSIS (since {since[:10]}) ====")
print(f"sessions: {len(sess)}   messages: {len(msgs)}   "
      f"users: {len({(meta.get(s,{}).get('user_id') or 'anon') for s in sess})}\n")

print("---- DAILY ACTIVITY ----")
for d in sorted(daily):
    v = daily[d]
    print(f"  {d}: {len(v['sess']):>2} sessions | {v['u']:>3} questions | {v['a']:>3} answers | {v['err']:>2} errors")

print("\n---- TOOL USAGE ----")
for n, c in tool_hist.most_common():
    print(f"  {c:>4}  {n}")
print(f"  [study cheat-sheets={study} quizzes={quiz} drafting={drafting} web/gov searches={websearch}]")

print(f"\n---- FAILURES / FRICTION ({len(errors)}) ----")
for d, uid, q, kind in errors[:25]:
    print(f"  [{d}] {kind:<12} u={uid}  {q}")

print(f"\n---- REPEATED QUESTIONS (retry/frustration signal) ----")
for uid, q, c in sorted(retries, key=lambda x:-x[2])[:15]:
    print(f"  x{c}  u={uid}  {q}")

print("\n---- SESSION ROSTER (newest first) ----")
for sid, ms in sorted(sess.items(), key=lambda kv: kv[1][-1]["created_at"], reverse=True)[:25]:
    m = meta.get(sid, {})
    uid = (m.get("user_id") or "ANON")[:8]
    when = (ms[-1]["created_at"] or "")[:16].replace("T", " ")
    us = [x for x in ms if x["role"]=="user"]; asx=[x for x in ms if x["role"]=="assistant"]
    print(f"  [{when}] u={uid} ({len(us)}q/{len(asx)}a) {short(m.get('title'),46)}")
    for u in us[:3]:
        print(f"        Q: {short(u.get('content'),85)}")
