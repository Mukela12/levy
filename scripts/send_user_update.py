"""Send a Levy product update to everyone with an account.

The owner runs this himself. It needs the email admin token, which only he
holds; the script asks for it at a hidden prompt, never writes it anywhere
and never prints it. It never prints an email address either.

    backend/.venv/bin/python scripts/send_user_update.py
        Dry run. Builds the list, asks the live site what it would send, and
        prints the subject and the count. Nothing is sent.

    backend/.venv/bin/python scripts/send_user_update.py --preview-to you@example.com
        One copy to that address, with "Preview |" in the subject.

    backend/.venv/bin/python scripts/send_user_update.py --send
        Shows the subject and the count, asks you to type the count, sends,
        and saves who got which message id to a private file outside the repo.

Who gets it: every account with a confirmed address, less test and example
addresses, the QA probe, and anyone listed in the unsubscribe file (one
address a line; default ~/levy-research/broadcasts/unsubscribed.txt).

A broadcast cannot be recalled: run the dry run and the preview first.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTE = "https://www.levylegal.ai/api/email/product-update"
PRIVATE_DIR = Path.home() / "levy-research" / "broadcasts"
NOT_PEOPLE = ("levy-qa-probe@",)
TEST_DOMAINS = ("example.com", "example.org", "example.net", "test.com")


def unsubscribed(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {ln.strip().lower() for ln in path.read_text().splitlines() if "@" in ln and not ln.lstrip().startswith("#")}


def recipients(exclude: set[str]) -> tuple[list[str], dict[str, int]]:
    """Addresses to send to, and how many accounts were left out and why."""
    env = ROOT / "backend" / ".env"
    if not env.exists():                       # a worktree has no .env of its own
        env = Path.home() / "levy" / "backend" / ".env"
    from dotenv import load_dotenv
    load_dotenv(env)
    sys.path.insert(0, str(ROOT / "backend"))
    from app.db.supabase import get_db

    db = get_db()
    users, page = [], 1
    while True:
        batch = db.auth.admin.list_users(page=page, per_page=200)
        users += batch
        if len(batch) < 200:
            break
        page += 1

    left_out = {"no address": 0, "test or example address": 0, "address not confirmed": 0, "unsubscribed": 0}
    out: list[str] = []
    for u in users:
        email = (u.email or "").strip().lower()
        domain = email.rsplit("@", 1)[-1]
        if "@" not in email:
            left_out["no address"] += 1
        elif email.startswith(NOT_PEOPLE) or domain in TEST_DOMAINS or domain.endswith((".test", ".example", ".invalid")):
            left_out["test or example address"] += 1
        elif not getattr(u, "email_confirmed_at", None):
            left_out["address not confirmed"] += 1
        elif email in exclude:
            left_out["unsubscribed"] += 1
        elif email not in out:
            out.append(email)
    return out, left_out


def post(token: str, payload: dict) -> dict:
    import httpx
    r = httpx.post(ROUTE, headers={"x-levy-email-token": token}, json=payload, timeout=600)
    if r.status_code == 403:
        sys.exit("The site refused the token. Check it is the current LEVY_EMAIL_ADMIN_TOKEN and that the site was redeployed after it was set.")
    try:
        body = r.json()
    except ValueError:
        sys.exit(f"The site answered {r.status_code} with something that is not JSON.")
    if r.status_code >= 400:
        sys.exit(f"The site answered {r.status_code}: {body.get('error', 'no reason given')}")
    return body


def main() -> None:
    ap = argparse.ArgumentParser(description="Send a Levy product update. A dry run unless --send or --preview-to is given.")
    ap.add_argument("--edition", help="which update to send (default: the site's latest)")
    ap.add_argument("--preview-to", metavar="ADDRESS", help="send one copy, marked Preview, to this address only")
    ap.add_argument("--send", action="store_true", help="send to everyone on the list")
    ap.add_argument("--count-only", action="store_true", help="count the list and stop, without contacting the site")
    ap.add_argument("--unsubscribed", type=Path, default=PRIVATE_DIR / "unsubscribed.txt",
                    help="file of addresses that asked not to be emailed, one a line")
    args = ap.parse_args()

    people, left_out = recipients(unsubscribed(args.unsubscribed))
    print(f"On the list: {len(people)} accounts.")
    for why, n in left_out.items():
        if n:
            print(f"  left out, {why}: {n}")
    if args.count_only:
        return

    token = os.environ.get("LEVY_EMAIL_ADMIN_TOKEN") or getpass.getpass("Email admin token (hidden): ").strip()
    if not token:
        sys.exit("No token given.")
    base = {"edition": args.edition} if args.edition else {}

    if args.preview_to:
        out = post(token, {**base, "recipients": [args.preview_to], "preview": True})
        print(f"Preview: sent {out.get('sent', 0)}, failed {out.get('failed', 0)}. Check that inbox on a phone and a computer.")
        return

    dry = post(token, {**base, "recipients": people, "dryRun": True})
    print(f"Edition: {dry.get('edition')}\nSubject: {dry.get('subject')}\nThe site would send to: {dry.get('wouldSendTo')}")
    if dry.get("wouldSendTo") != len(people):
        sys.exit("The site's count differs from the list's. Nothing sent.")
    if not args.send:
        print("Dry run only. Nothing was sent. Add --send to send.")
        return

    typed = input(f"Type {len(people)} to send this to {len(people)} people. It cannot be recalled: ").strip()
    if typed != str(len(people)):
        sys.exit("Not confirmed. Nothing sent.")
    out = post(token, {**base, "recipients": people})
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    record = PRIVATE_DIR / f"{dry.get('edition')}-{datetime.now():%Y-%m-%d-%H%M}.json"
    record.write_text(json.dumps({"subject": dry.get("subject"), **out}, indent=1))
    record.chmod(0o600)
    print(f"Sent {out.get('sent', 0)}, failed {out.get('failed', 0)}. The record (private, it holds addresses) is at {record}")
    if out.get("failed"):
        print("Some failed. The record lists them with the reason; they were not sent, so they can be retried by hand.")


if __name__ == "__main__":
    main()
