"""Levy News review, shadow mode: what the editor sees and decides.

Admin only. Every route needs the ADMIN_API_TOKEN secret as the X-Admin-Token
header, like the artifact sweep. Nothing here is visible to users. Approving a
check records the editor's decision for the accuracy record; it does not
publish anything.
"""
from __future__ import annotations

import hmac
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..config import get_settings
from ..db.supabase import get_db

router = APIRouter(prefix="/api/admin/news")
STATUSES = ("pending", "held", "approved", "rejected")
DECISIONS = {"approve": "approved", "reject": "rejected", "hold": "held", "reopen": "pending"}
STORY_FIELDS = "id,title,category,risk,check_worthy,item_count,outlet_count,social_count,first_seen_at,last_seen_at"


def require_admin(token: str | None) -> None:
    expected = getattr(get_settings(), "admin_api_token", "") or os.environ.get("ADMIN_API_TOKEN", "")
    if not expected or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="admin token required")


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise HTTPException(status_code=404, detail="check not found") from None


@router.get("/checks")
def list_checks(status: str = "pending", limit: int = 50, x_admin_token: str | None = Header(default=None)):
    """Checks waiting for (or past) the editor, newest first, with the coverage behind each story."""
    require_admin(x_admin_token)
    if status not in STATUSES + ("all",):
        raise HTTPException(status_code=400, detail=f"status must be one of {', '.join(STATUSES)} or all")
    db = get_db()
    q = db.table("news_checks").select(f"*, news_stories({STORY_FIELDS})")
    if status != "all":
        q = q.eq("review_status", status)
    checks = q.order("created_at", desc=True).limit(max(1, min(limit, 200))).execute().data or []
    story_ids = sorted({c["story_id"] for c in checks})
    coverage: dict[str, list[dict]] = {}
    for k in range(0, len(story_ids), 50):
        rows = (db.table("news_story_items").select("story_id, news_items(outlet,outlet_type,title,url,published_at)")
                .in_("story_id", story_ids[k:k + 50]).execute().data or [])
        for r in rows:
            if r.get("news_items"):
                coverage.setdefault(r["story_id"], []).append(r["news_items"])
    counts = {s: db.table("news_checks").select("id", count="exact").eq("review_status", s).limit(1).execute().count or 0
              for s in STATUSES}
    return {"checks": [{**c, "coverage": coverage.get(c["story_id"], [])} for c in checks], "counts": counts}


class Review(BaseModel):
    action: Literal["approve", "reject", "hold", "reopen"]
    note: str | None = Field(default=None, max_length=1000)


@router.post("/checks/{check_id}/review")
def review_check(check_id: str, body: Review, x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)
    check_id = _uuid(check_id)
    status = DECISIONS[body.action]
    rows = (get_db().table("news_checks")
            .update({"review_status": status, "review_note": (body.note or "").strip() or None,
                     "reviewed_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", check_id).execute().data)
    if not rows:
        raise HTTPException(status_code=404, detail="check not found")
    return {"id": check_id, "review_status": status}


@router.get("/runs")
def list_runs(limit: int = 10, x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)
    rows = get_db().table("news_runs").select("*").order("started_at", desc=True).limit(max(1, min(limit, 50))).execute().data
    from ..services.news import pipeline
    return {"runs": rows or [], "running": pipeline.RUN_LOCK.locked(), "watch_hours": pipeline.hours_from_env()}


@router.post("/run")
def run_now(max_checks: int = 3, budget_usd: float = 0.5, x_admin_token: str | None = Header(default=None)):
    """Start a run in the background. Capped: at most 10 checks and $2 a run."""
    require_admin(x_admin_token)
    from ..services.news import pipeline
    if pipeline.RUN_LOCK.locked():
        raise HTTPException(status_code=409, detail="a run is already in progress")
    max_checks, budget_usd = max(1, min(max_checks, 10)), max(0.05, min(budget_usd, 2.0))
    threading.Thread(target=pipeline.run_once, kwargs={"max_checks": max_checks, "budget_usd": budget_usd},
                     daemon=True).start()
    return {"started": True, "max_checks": max_checks, "budget_usd": budget_usd}
