"""Which questions go to the stronger model.

Most of what Levy is asked (leave days, a notice period, how to register a
business) is answered well by the everyday model. A few questions are the
kind a senior lawyer would slow down for: hunting for authority on a
proposition, drafting arguments or pleadings, advising on a client's
position. Those go to `hard_task_model`, which costs twice as much per
token, so the choice has to be cheap, predictable and capped.

It is decided from the question's own words, with no extra model call: a
classifier in front of every answer would add a wait to all of them to
upgrade a few. A short follow-up ("answer it", "yes, draft that") stays on
the stronger model when the question before it was a hard one.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

# Asking for authority on a proposition. "Authority" alone is not enough:
# "local authority", "Zambia Revenue Authority".
_AUTHORITY = re.compile(
    r"\bauthorit(?:y|ies)\s+(?:that|which|for|on|to the effect|speak|support|hold|say)"
    r"|\b(?:legal|case|judicial|binding|persuasive)\s+authorit(?:y|ies)\b"
    r"|\bprecedents?\b|\bcase[- ]law\b|\b(?:decided|leading|reported)\s+cases?\b|\bwhich case\b"
    r"|\bcases?\s+(?:that|which|where)\s+(?:speak|hold|held|decid|deal|support|say|address)", re.I)
# Litigation drafting and formal opinions.
_DRAFTING = re.compile(
    r"\b(?:skeleton arguments?|heads of arguments?|written submissions?"
    r"|(?:submissions?|arguments?)\s+in\s+(?:support|opposition|reply)|grounds of appeal|notice of appeal"
    r"|memorandum of appeal|record of appeal|affidavit in (?:support|opposition|reply)|statement of claim"
    r"|defence and counter-?claim|originating (?:summons|notice of motion|process)"
    r"|legal opinion|opinion on the merits)\b", re.I)
# A practitioner's question about a client's position.
_ADVOCACY = re.compile(
    r"\b(?:my|our)\s+client\b|\bhow\s+(?:would|do|should|can)\s+(?:you|i|we)\s+argue\b"
    r"|\bprospects of success\b|\bmerits of (?:the|my|our|an?)\s+(?:case|appeal|claim|application|defence)\b", re.I)

FOLLOW_UP_CHARS = 120


def _signals(text: str) -> list[str]:
    out = []
    if _AUTHORITY.search(text or ""):
        out.append("authority")
    if _DRAFTING.search(text or ""):
        out.append("drafting")
    if _ADVOCACY.search(text or ""):
        out.append("advocacy")
    return out


def hard_task(query: str, history: list[dict] | None = None) -> str | None:
    """Why this question is a hard one ("authority", "drafting", "advocacy",
    "follow_up"), or None when the everyday model should answer it."""
    found = _signals(query)
    if found:
        return found[0]
    if len((query or "").strip()) <= FOLLOW_UP_CHARS:
        for m in reversed(history or []):
            if isinstance(m, dict) and m.get("role") == "user":
                prev = m.get("content")
                prev = prev if isinstance(prev, str) else " ".join(
                    b.get("text", "") for b in (prev or []) if isinstance(b, dict))
                return "follow_up" if _signals(prev) else None
    return None


def budget_ok(owner_id: str | None) -> bool:
    """Is there room today for one more answer from the stronger model?

    Counts today's (UTC) saved answers by that model, for everyone and for
    this user. Any failure to count answers "no": the cap exists to bound
    spend, so doubt stays on the cheaper model.
    """
    from ..config import get_settings
    from ..db.supabase import get_db
    s = get_settings()
    if not owner_id:
        return False
    try:
        db = get_db()
        midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        total = (db.table("chat_messages").select("id", count="exact").eq("role", "assistant")
                 .eq("model", s.hard_task_model).gte("created_at", midnight).limit(1).execute().count or 0)
        if total >= int(s.hard_task_daily_cap):
            return False
        sessions = [r["id"] for r in (db.table("chat_sessions").select("id").eq("user_id", owner_id)
                                      .gte("updated_at", midnight).limit(200).execute().data or [])]
        if not sessions:
            return True
        mine = (db.table("chat_messages").select("id", count="exact").eq("role", "assistant")
                .eq("model", s.hard_task_model).gte("created_at", midnight).in_("session_id", sessions)
                .limit(1).execute().count or 0)
        return mine < int(s.hard_task_user_daily_cap)
    except Exception:  # noqa: BLE001
        return False
