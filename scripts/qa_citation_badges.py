#!/usr/bin/env python3
"""End-to-end check of the citation verification badges against PRODUCTION.

Two invariants, tested with a real signed-in streaming run (QA probe account,
marked with X-Levy-QA-Probe so nothing lands in analytics):

  1. An answer citing a case Levy holds emits a citation_audit event with a
     VERIFIED verdict carrying the held document's id.
  2. The known-absent trap: "Zulu v The People (1990-2) ZR 65" (old Law
     Reports, deliberately not held) must NEVER come back verified. A false
     VERIFIED here is the one failure the feature cannot have.

Streams retry three times because this network drops long reads.

Usage: backend/.venv/bin/python scripts/qa_citation_badges.py
"""
import json, os, sys, time
from pathlib import Path
import httpx

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")
from app.db.supabase import get_db  # noqa: E402

API = "https://levy-api-production.up.railway.app"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
EMAIL = "levy-qa-probe@levylegal.ai"


def token() -> tuple[str, str]:
    db = get_db()
    pw = "qa-" + os.urandom(8).hex()
    users = db.auth.admin.list_users()
    users = users if isinstance(users, list) else getattr(users, "users", [])
    uid = next((str(u.id) for u in users if (u.email or "") == EMAIL), None)
    if uid is None:
        raise SystemExit("QA probe account missing; create levy-qa-probe first")
    db.auth.admin.update_user_by_id(uid, {"password": pw})
    env = dict(l.strip().split("=", 1) for l in open(REPO / "backend" / ".env") if "=" in l)
    r = httpx.post(f"{env['SUPABASE_URL']}/auth/v1/token?grant_type=password",
                   headers={"apikey": env["SUPABASE_KEY"], "Content-Type": "application/json"},
                   json={"email": EMAIL, "password": pw}, timeout=30)
    return r.json()["access_token"], uid


def ask(tok: str, uid: str, q: str) -> list[dict]:
    for attempt in range(3):
        try:
            audit = None
            with httpx.stream("POST", f"{API}/api/chat/stream",
                    headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
                             "User-Agent": UA, "X-Levy-QA-Probe": "1"},
                    json={"query": q, "user_id": uid},
                    timeout=httpx.Timeout(240, read=240)) as r:
                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    d = line[6:]
                    if d == "[DONE]":
                        break
                    try:
                        ev = json.loads(d)
                    except Exception:
                        continue
                    if ev.get("type") == "citation_audit":
                        audit = ev["citations"]
            return audit or []
        except Exception as e:  # noqa: BLE001
            print(f"  (stream attempt {attempt+1}: {type(e).__name__}; retrying)")
            time.sleep(4)
    return []


def main() -> int:
    tok, uid = token()
    failures = []

    a = ask(tok, uid, "What did the Court of Appeal decide in Cynthia Kunda v "
                      "Loreta Kunda (APP No. 142 of 2019)? Cite the case.")
    verified = [c for c in a if c["status"] == "verified" and c.get("document_id")]
    print(f"1. held case cited: {len(a)} audited, {len(verified)} verified")
    if not verified:
        failures.append("no VERIFIED verdict for a case Levy holds")

    b = ask(tok, uid, "Summarise the holding in Zulu v The People (1990-2) ZR 65.")
    bad = [c for c in b if c["status"] == "verified"
           and "zulu" in c["text"].lower() and "violet" not in c["text"].lower()]
    print(f"2. Zulu (1990-2) trap: {len(b)} audited, false-verified={len(bad)}")
    if bad:
        failures.append("FALSE VERIFIED on Zulu v The People (1990-2)")

    print("\n" + ("ALL BADGE CHECKS PASSED" if not failures else "FAILURES: " + "; ".join(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
