#!/usr/bin/env python3
"""Read-only: dump one user's profile + full question text, to check where they
are and which country's law they are actually asking about.

Usage: python scripts/who_is_user.py <substring-of-email-or-name>
"""
from __future__ import annotations
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
import _dns_resilient  # noqa: F401  (must be first — flaky local DNS)
from dotenv import load_dotenv
load_dotenv(REPO / "backend" / ".env")
from app.db.supabase import get_db

needle = (sys.argv[1] if len(sys.argv) > 1 else "rohanda").lower()
db = get_db()

users = db.auth.admin.list_users()
hits = [u for u in users if needle in (u.email or "").lower()
        or needle in str(u.user_metadata or {}).lower()]

for u in hits:
    print("=" * 78)
    print("EMAIL      ", u.email)
    print("CREATED    ", u.created_at)
    print("LAST SIGNIN", u.last_sign_in_at)
    print("METADATA   ", u.user_metadata)
    print("APP META   ", u.app_metadata)
    print()

    sess = (db.table("chat_sessions").select("id,title,created_at")
            .eq("user_id", u.id).order("created_at").execute().data or [])
    print(f"{len(sess)} session(s)")
    for s in sess:
        print("-" * 78)
        print(f"[{s['created_at'][:16]}]  {s.get('title')}")
        msgs = (db.table("chat_messages").select("role,content,created_at")
                .eq("session_id", s["id"]).order("created_at").execute().data or [])
        for m in msgs:
            if m["role"] != "user":
                continue
            print("  Q:", (m.get("content") or "").strip().replace("\n", " ")[:600])
