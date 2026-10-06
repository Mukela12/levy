#!/usr/bin/env python3
"""Ask Levy the benchmark questions and save the answers for grading.

Signs in as the QA probe, which analytics excludes, and streams each answer
from the live API so the run measures what a user actually gets, not a local
build. One full answer per question, so a run costs what nine answers cost.

  python bench/run_levy.py                      # all questions
  python bench/run_levy.py --only meal-break
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT.parent / "backend" / ".env")
from app.db.supabase import get_db  # noqa: E402

API = os.environ.get("LEVY_API", "https://levy-api-production.up.railway.app")
EMAIL = "levy-qa-probe@levylegal.ai"


def probe_token() -> str:
    db = get_db()
    password = "qa-" + os.urandom(8).hex()
    users = db.auth.admin.list_users()
    users = users if isinstance(users, list) else getattr(users, "users", [])
    uid = next(str(u.id) for u in users if (u.email or "") == EMAIL)
    db.auth.admin.update_user_by_id(uid, {"password": password})
    r = httpx.post(
        f"{os.environ['SUPABASE_URL']}/auth/v1/token?grant_type=password",
        headers={"apikey": os.environ["SUPABASE_KEY"], "Content-Type": "application/json"},
        json={"email": EMAIL, "password": password}, timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


ANSWERED_BY: list = []


def ask(token: str, question: str, model: str | None = None) -> tuple[str, float, int]:
    """Return (answer, seconds, tool_calls). Each question starts a fresh thread."""
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Levy-QA-Probe": "1",
        # _BOT_UA 403s python-httpx even when signed in.
        "User-Agent": "Mozilla/5.0 (Macintosh; Levy benchmark)",
        "Content-Type": "application/json",
    }
    body = {"query": question, "web_search": True}
    if model:
        # Honoured by the API only for Sonnet 5.5, Sonnet 4.6 and Haiku 4.5.
        body["model"] = model
    started = time.time()
    out, tools = [], 0
    with httpx.Client(timeout=httpx.Timeout(600, read=600)) as c:
        with c.stream("POST", f"{API}/api/chat/stream", headers=headers, json=body) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "done":
                    ANSWERED_BY.append(event.get("model"))
                if event.get("type") == "token":
                    out.append(event.get("content") or "")
                elif event.get("type") == "tool_call":
                    tools += 1
    return "".join(out), round(time.time() - started, 1), tools


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", help="question id; repeatable")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--model", help="claude-sonnet-5-5 | claude-sonnet-4-6 | claude-haiku-4-5")
    args = ap.parse_args()

    questions = json.loads((ROOT / "questions.json").read_text())
    if args.only:
        questions = [q for q in questions if q["id"] in set(args.only)]
    date = dt.date.today().isoformat()
    out_path = args.out or ROOT / "results" / f"{date}-levy{'-' + args.model if args.model else ''}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    token = probe_token()
    answers = []
    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q['id']}", flush=True)
        # A long answer over a mobile-grade connection drops sometimes: the
        # first run of this benchmark lost a question to an incomplete chunked
        # read. The run is detached server-side and the duplicate guard keys on
        # the thread, and these have no thread, so simply asking again is safe.
        text = ""
        for attempt in (1, 2, 3):
            try:
                text, secs, tools = ask(token, q["question"], args.model)
                break
            except Exception as e:  # noqa: BLE001 — one bad question must not lose the run
                print(f"    attempt {attempt} failed: {str(e)[:80]}", flush=True)
                if attempt == 3:
                    answers.append({"id": q["id"], "answer": "", "error": str(e)[:200]})
                time.sleep(5)
        if not text:
            continue
        print(f"    {len(text)} chars, {secs}s, {tools} tool calls", flush=True)
        answers.append({"id": q["id"], "answer": text, "seconds": secs, "tool_calls": tools,
                        "answered_by": ANSWERED_BY[-1] if ANSWERED_BY else None})

    out_path.write_text(json.dumps(
        {"model": f"levy-{args.model}" if args.model else "levy", "date": date, "api": API, "answers": answers}, indent=1))
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
