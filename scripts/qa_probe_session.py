#!/usr/bin/env python3
"""Mint a short-lived browser session for the QA probe account so a preview
can be driven signed in. Rotates the probe's password (as the other QA
scripts do) and writes a cookie payload the @supabase/ssr client reads.
Prints only lengths; the payload goes to the path given.
  backend/.venv/bin/python scripts/qa_probe_session.py --out <file>
"""
import argparse, base64, json, os, sys
from pathlib import Path
import httpx
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")
from app.db.supabase import get_db  # noqa: E402
EMAIL = "levy-qa-probe@levylegal.ai"

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args()
    db = get_db(); pw = "qa-" + os.urandom(8).hex()
    users = db.auth.admin.list_users(); users = users if isinstance(users, list) else getattr(users, "users", [])
    uid = next((str(u.id) for u in users if (u.email or "") == EMAIL), None)
    if not uid: raise SystemExit("QA probe account missing")
    db.auth.admin.update_user_by_id(uid, {"password": pw})
    env = dict(l.strip().split("=", 1) for l in open(REPO / "backend" / ".env") if "=" in l)
    url, anon = env["SUPABASE_URL"], env["SUPABASE_KEY"]
    r = httpx.post(f"{url}/auth/v1/token?grant_type=password", headers={"apikey": anon, "Content-Type": "application/json"},
                   json={"email": EMAIL, "password": pw}, timeout=30)
    r.raise_for_status(); s = r.json()
    session = {"access_token": s["access_token"], "refresh_token": s["refresh_token"], "expires_in": s["expires_in"],
               "expires_at": s.get("expires_at"), "token_type": "bearer", "user": s["user"]}
    ref = url.split("//")[1].split(".")[0]
    payload = "base64-" + base64.urlsafe_b64encode(json.dumps(session).encode()).decode().rstrip("=")
    Path(a.out).write_text(json.dumps({"name": f"sb-{ref}-auth-token", "value": payload}))
    os.chmod(a.out, 0o600)
    print(f"session written: cookie {len(payload)} chars, user {uid[:8]}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
