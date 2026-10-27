"""Where Levy News keeps its items, stories, checks and runs.

SupabaseStore writes the news_* tables (supabase/migrations/20261027000000_levy_news.sql).
MemoryStore holds the same in memory and writes one JSON file, for a dry run
before the tables exist, or in tests.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

CHUNK = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _counts(items: list[dict]) -> dict:
    """Coverage numbers for a story from its items."""
    times = sorted(i["published_at"] or i.get("fetched_at") or _now() for i in items) or [_now()]
    return {"item_count": len(items), "outlet_count": len({i["outlet"] for i in items}),
            "social_count": sum(1 for i in items if i["outlet_type"] == "social"),
            "first_seen_at": times[0], "last_seen_at": times[-1]}


def rank_key(s: dict) -> tuple:
    """Most check-worthy first, then stories spreading on social media, then wider coverage, then newest."""
    try:
        newest = -datetime.fromisoformat(s.get("last_seen_at") or "").timestamp()
    except ValueError:
        newest = 0.0
    return (-s.get("check_worthy", 0), -s.get("social_count", 0), -s.get("outlet_count", 0), newest)


class SupabaseStore:
    def __init__(self, db=None):
        if db is None:
            from ...db.supabase import get_db
            db = get_db()
        self.db = db

    def filter_new(self, items: list[dict]) -> list[dict]:
        hashes = [i["url_hash"] for i in items]
        known: set[str] = set()
        for k in range(0, len(hashes), CHUNK):
            rows = self.db.table("news_items").select("url_hash").in_("url_hash", hashes[k:k + CHUNK]).execute().data or []
            known |= {r["url_hash"] for r in rows}
        return [i for i in items if i["url_hash"] not in known]

    def insert_items(self, items: list[dict]) -> list[dict]:
        out = []
        cols = ("url", "url_hash", "outlet", "outlet_type", "title", "summary", "published_at", "feed")
        for k in range(0, len(items), CHUNK):
            rows = [{c: i.get(c) for c in cols} for i in items[k:k + CHUNK]]
            out += self.db.table("news_items").upsert(rows, on_conflict="url_hash").execute().data or []
        return out

    def recent_stories(self, hours: float = 72, limit: int = 40) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        return (self.db.table("news_stories").select("id,title,claim,first_seen_at").gte("last_seen_at", since)
                .order("last_seen_at", desc=True).limit(limit).execute().data or [])

    def create_stories(self, stories: list[dict]) -> dict[str, str]:
        ids = {}
        for s in stories:
            row = {"title": s["title"][:300], "claim": s.get("claim") or None, "category": s.get("category"),
                   "risk": s.get("risk") or {}, "check_worthy": s.get("check_worthy", 0),
                   "first_seen_at": s.get("first_seen_at") or _now(), "last_seen_at": s.get("first_seen_at") or _now(),
                   "status": "new" if s.get("claim") and s.get("check_worthy", 0) >= 2 else "skipped"}
            ids[s["key"]] = self.db.table("news_stories").insert(row).execute().data[0]["id"]
        return ids

    def attach(self, pairs: list[tuple[str, str]]) -> None:
        rows = [{"story_id": s, "item_id": i} for s, i in pairs]
        for k in range(0, len(rows), CHUNK):
            self.db.table("news_story_items").upsert(rows[k:k + CHUNK]).execute()

    def story_items(self, story_id: str) -> list[dict]:
        rows = (self.db.table("news_story_items").select("news_items(id,url,outlet,outlet_type,title,published_at,fetched_at)")
                .eq("story_id", story_id).execute().data or [])
        return [r["news_items"] for r in rows if r.get("news_items")]

    def refresh_counts(self, story_ids) -> None:
        for sid in story_ids:
            items = self.story_items(sid)
            if items:
                self.db.table("news_stories").update(_counts(items)).eq("id", sid).execute()

    def candidates(self, limit: int, hours: float = 72) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = (self.db.table("news_stories").select("*").eq("status", "new").gte("check_worthy", 2)
                .gte("last_seen_at", since).limit(200).execute().data or [])
        return sorted((r for r in rows if r.get("claim")), key=rank_key)[:limit]

    def save_check(self, row: dict) -> None:
        prior = (self.db.table("news_checks").select("version").eq("story_id", row["story_id"])
                 .order("version", desc=True).limit(1).execute().data or [])
        self.db.table("news_checks").insert({**row, "version": (prior[0]["version"] + 1) if prior else 1}).execute()
        self.mark_story(row["story_id"], "checked")

    def mark_story(self, story_id: str, status: str) -> None:
        self.db.table("news_stories").update({"status": status}).eq("id", story_id).execute()

    def start_run(self) -> str:
        return self.db.table("news_runs").insert({"started_at": _now()}).execute().data[0]["id"]

    def finish_run(self, run_id: str, fields: dict) -> None:
        self.db.table("news_runs").update({**fields, "finished_at": _now()}).eq("id", run_id).execute()

    def last_run_at(self) -> datetime | None:
        rows = self.db.table("news_runs").select("started_at").order("started_at", desc=True).limit(1).execute().data
        return datetime.fromisoformat(rows[0]["started_at"]) if rows else None


class MemoryStore:
    """The same interface, in memory; `dump` writes everything to one JSON file."""

    def __init__(self):
        self.items: dict[str, dict] = {}
        self.stories: dict[str, dict] = {}
        self.links: set[tuple[str, str]] = set()
        self.checks: list[dict] = []
        self.runs: list[dict] = []

    def filter_new(self, items):
        return [i for i in items if i["url_hash"] not in {x["url_hash"] for x in self.items.values()}]

    def insert_items(self, items):
        out = []
        for i in items:
            row = {**i, "id": str(uuid.uuid4()), "fetched_at": _now()}
            self.items[row["id"]] = row
            out.append(row)
        return out

    def recent_stories(self, hours=72, limit=40):
        return [{k: s[k] for k in ("id", "title", "claim", "first_seen_at")} for s in list(self.stories.values())[-limit:]]

    def create_stories(self, stories):
        ids = {}
        for s in stories:
            sid = str(uuid.uuid4())
            self.stories[sid] = {"id": sid, "title": s["title"], "claim": s.get("claim") or None,
                                 "category": s.get("category"), "risk": s.get("risk") or {},
                                 "check_worthy": s.get("check_worthy", 0), "first_seen_at": s.get("first_seen_at") or _now(),
                                 "last_seen_at": s.get("first_seen_at") or _now(),
                                 "status": "new" if s.get("claim") and s.get("check_worthy", 0) >= 2 else "skipped"}
            ids[s["key"]] = sid
        return ids

    def attach(self, pairs):
        self.links |= set(pairs)

    def story_items(self, story_id):
        return [self.items[i] for s, i in self.links if s == story_id]

    def refresh_counts(self, story_ids):
        for sid in story_ids:
            items = self.story_items(sid)
            if items:
                self.stories[sid].update(_counts(items))

    def candidates(self, limit, hours=72):
        rows = [s for s in self.stories.values() if s["status"] == "new" and s.get("claim") and s["check_worthy"] >= 2]
        return sorted(rows, key=rank_key)[:limit]

    def save_check(self, row):
        self.checks.append({**row, "version": 1, "created_at": _now()})
        self.mark_story(row["story_id"], "checked")

    def mark_story(self, story_id, status):
        self.stories[story_id]["status"] = status

    def start_run(self):
        self.runs.append({"id": str(uuid.uuid4()), "started_at": _now()})
        return self.runs[-1]["id"]

    def finish_run(self, run_id, fields):
        self.runs[-1].update({**fields, "finished_at": _now()})

    def last_run_at(self):
        return None

    def dump(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"runs": self.runs, "checks": self.checks, "stories": list(self.stories.values()),
                                    "items": list(self.items.values()), "links": sorted(self.links)}, indent=1, default=str))
