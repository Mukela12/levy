#!/usr/bin/env python3
"""A weekly quality scorecard for Levy's real answers, from what each answer already records.

Levy has had one genuine thumbs rating in its life, so waiting for feedback
measures nothing. Every saved answer already carries the model that wrote it,
every tool call with its status, and the citation audit's verdicts; this reads
those, plus one behavioural signal no one has to click: a user re-asking the
same question within minutes, which is how people say an answer missed.

    python scripts/quality_report.py              # last 7 days
    python scripts/quality_report.py --days 14

Read-only. Excludes the owner's accounts and the QA probe. Prints no message
text, only counts and anonymised ids.
"""
from __future__ import annotations

import argparse
import re
import sys
import types
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))
from app.db.supabase import get_db  # noqa: E402

# Owner, owner's second account (benchmarks), QA probe, and two scripted test
# accounts found in the 6 Oct 2026 corrections review (hard-coded template
# UUIDs fired repeatedly; prompts beginning "For QA only"): not real usage.
EXCLUDE_PREFIXES = ("0bb36a24", "c391a7a2", "e49f9bea", "e1b20d71", "ffcdfb84")
PRIMARY = ("claude-sonnet-5-5", "claude-sonnet-4-6", "claude-opus-5-5")
REASK_MINUTES = 5
REASK_OVERLAP = 0.5
WORD = re.compile(r"[a-z]{4,}")


def words(text: str) -> set[str]:
    return set(WORD.findall((text or "").lower()))


def page(q, size=1000):
    out, i = [], 0
    while True:
        rows = q.range(i, i + size - 1).execute().data or []
        out += rows
        if len(rows) < size:
            return out
        i += size


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()
    db = get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()

    sessions = page(db.table("chat_sessions").select("id,user_id").gte("updated_at", since))
    sessions = [s for s in sessions if not str(s["user_id"]).startswith(EXCLUDE_PREFIXES)]
    owner_of = {s["id"]: s["user_id"] for s in sessions}
    msgs = []
    ids = list(owner_of)
    for i in range(0, len(ids), 100):
        msgs += page(db.table("chat_messages")
                     .select("id,session_id,role,content,created_at,model,provider,tool_calls,blocks")
                     .in_("session_id", ids[i:i + 100]).gte("created_at", since))
    msgs.sort(key=lambda m: (m["session_id"], m["created_at"]))
    answers = [m for m in msgs if m["role"] == "assistant"]
    questions = [m for m in msgs if m["role"] == "user"]
    if not answers:
        print(f"No real answers in the last {args.days} days.")
        return 0

    n = len(answers)
    pct = lambda k: f"{k} ({100 * k / n:.0f}%)" if n else "0"  # noqa: E731
    models = Counter(m.get("model") or "unrecorded" for m in answers)
    fallback = sum(c for mdl, c in models.items() if mdl not in PRIMARY and mdl != "unrecorded")
    # A turn that hands the user a clarifying question (ask_user) has no prose by
    # design; counting it as an empty answer made 6 of 40 look broken on 12 Oct.
    asked = lambda m: any(c.get("name") == "ask_user" for c in (m.get("tool_calls") or []))  # noqa: E731
    empty = sum(1 for m in answers if len((m.get("content") or "").strip()) < 200 and not asked(m))
    clarifying = sum(1 for m in answers if asked(m))

    tool_runs, tool_errors = Counter(), Counter()
    misses = 0
    for m in answers:
        calls = m.get("tool_calls") or []
        for c in calls:
            tool_runs[c.get("name")] += 1
            if c.get("status") == "error":
                tool_errors[c.get("name")] += 1
        searches = [c for c in calls if c.get("name") == "search_corpus"]
        if searches and not any(c.get("db") for c in searches):
            misses += 1

    not_found = dead_cited = audited = 0
    for m in answers:
        audit = next((b for b in (m.get("blocks") or []) if b.get("kind") == "citation_audit"), None)
        if not audit:
            continue
        audited += 1
        cites = audit.get("citations") or []
        if any(c.get("status") == "not_found" and not c.get("foreign") for c in cites):
            not_found += 1
        if any((c.get("law_status") in ("repealed", "not in force") and not c.get("acknowledged"))
               or any(not d.get("acknowledged") for d in (c.get("section_status") or [])) for c in cites):
            dead_cited += 1

    # Re-asks: a user message soon after an answer that mostly repeats the
    # question before it. Rephrasing is how users say "that missed".
    reasks = 0
    by_session = defaultdict(list)
    for m in msgs:
        by_session[m["session_id"]].append(m)
    for convo in by_session.values():
        last_q, last_a_at = None, None
        for m in convo:
            t = datetime.fromisoformat(m["created_at"].replace("Z", "+00:00"))
            if m["role"] == "assistant":
                last_a_at = t
            elif m["role"] == "user":
                if last_q and last_a_at and (t - last_a_at) <= timedelta(minutes=REASK_MINUTES):
                    a, b = words(last_q), words(m.get("content"))
                    if a and b and len(a & b) / min(len(a), len(b)) >= REASK_OVERLAP:
                        reasks += 1
                last_q = m.get("content")

    fb = page(db.table("message_feedback").select("rating,user_id,created_at").gte("created_at", since))
    fb = [f for f in fb if not str(f["user_id"]).startswith(EXCLUDE_PREFIXES)]
    ratings = Counter(str(f.get("rating")) for f in fb)

    print(f"# Levy quality, last {args.days} days (real users only)\n")
    print(f"- users {len(set(owner_of.values()))}, chats {len({m['session_id'] for m in answers})}, "
          f"questions {len(questions)}, answers {n}")
    print(f"- answered by: " + ", ".join(f"{k} {v}" for k, v in models.most_common()))
    print(f"- fallback answers (not the primary Claude): {pct(fallback)}")
    print(f"- empty or very short answers (<200 chars): {pct(empty)}")
    print(f"- turns that asked the user a clarifying question: {pct(clarifying)}")
    print(f"- library misses (searched, nothing returned): {pct(misses)}")
    print(f"- re-asks within {REASK_MINUTES} min (rephrased question after an answer): {reasks}")
    print(f"- citation audit ran on {audited}; answers with a citation not found: {not_found}; "
          f"relying on repealed / not-in-force law without saying so: {dead_cited}")
    errs = ", ".join(f"{k} {v}/{tool_runs[k]}" for k, v in tool_errors.most_common(6)) or "none"
    print(f"- tool errors: {errs}")
    print(f"- thumbs: " + (", ".join(f"{k} {v}" for k, v in ratings.items()) or "none given"))

    # Is the answer's law traceable, and what did it cost? (17 Nov 2026: the
    # source check, ZambiaLII's index and per-answer cost logging.) Each cited
    # authority is counted once by how it was settled; "unverified" is the
    # number to drive down.
    settled, checks, check_kinds = Counter(), 0, Counter()
    cost_by_model, answers_by_model, costed, routed = Counter(), Counter(), 0, Counter()
    for m in answers:
        blocks = m.get("blocks") or []
        audit = next((b for b in blocks if b.get("kind") == "citation_audit"), None)
        for c in (audit or {}).get("citations") or []:
            if c.get("status") == "verified":
                settled["held in the library"] += 1
            elif c.get("foreign"):
                settled["foreign authority"] += 1
            elif (c.get("seen") or {}).get("in") in ("library", "official", "index") and not (c.get("seen") or {}).get("conflict"):
                settled[{"library": "named in a held source", "official": "read on an official site",
                         "index": "listed on ZambiaLII"}[c["seen"]["in"]]] += 1
            elif c.get("known") and not c["known"].get("year_conflict"):
                settled["cited by held judgments"] += 1
            elif c.get("disclaimed"):
                settled["flagged unverified by the answer"] += 1
            else:
                settled["UNVERIFIED"] += 1
        if (audit or {}).get("check"):
            checks += 1
            check_kinds.update(audit["check"].get("kinds") or (["library miss, no web search"] if audit["check"].get("missed") else []))
        usage = next((b for b in blocks if b.get("kind") == "usage"), None)
        if usage:
            costed += 1
            if usage.get("routed"):
                routed[usage["routed"]] += 1
            for model, row in (usage.get("by_model") or {}).items():
                cost_by_model[model] += row.get("usd_est") or 0
                answers_by_model[model] += 1
    total_cites = sum(settled.values())
    print("\n## Trust")
    if total_cites:
        print(f"- {total_cites} authorities cited: " + ", ".join(f"{k} {v}" for k, v in settled.most_common()))
        print(f"- unverified share: {100 * settled['UNVERIFIED'] / total_cites:.0f}%")
    print(f"- answers sent back by the source check: {checks}"
          + (" (" + ", ".join(f"{k} {v}" for k, v in check_kinds.most_common()) + ")" if check_kinds else ""))
    try:
        looks = page(db.table("case_index_lookups").select("purpose,status,latency_ms").gte("created_at", since))
        ok = [l for l in looks if l["status"] == "ok"]
        print(f"- ZambiaLII index: {len(looks)} calls, {len(ok)} answered"
              + (f", median {sorted(l['latency_ms'] or 0 for l in ok)[len(ok) // 2] / 1000:.1f}s" if ok else "")
              + "; by purpose " + (", ".join(f"{k} {v}" for k, v in Counter(l["purpose"] for l in looks).items()) or "none"))
    except Exception:  # noqa: BLE001 — the lookups table is optional
        print("- ZambiaLII index: no lookup log (table case_index_lookups not created)")
    print("\n## Cost (estimated from token counts; answers saved since cost logging began)")
    if costed:
        total = sum(cost_by_model.values())
        print(f"- {costed} answers costed, ${total:.2f} in all, ${total / costed:.3f} an answer")
        for model, usd in cost_by_model.most_common():
            print(f"  - {model}: {answers_by_model[model]} answers, ${usd:.2f}, ${usd / answers_by_model[model]:.3f} each")
        if routed:
            print("- sent to the stronger model: " + ", ".join(f"{k} {v}" for k, v in routed.most_common()))
    else:
        print("- none yet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
