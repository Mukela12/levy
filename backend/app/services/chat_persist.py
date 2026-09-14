"""Server-side accumulation + durable persistence of an agent run.

Tier-1 durable execution: the agent run is driven in a detached task so it
completes and saves the assistant message even when the client disconnects
(closed tab, locked phone, dropped mobile signal). This accumulator mirrors
the frontend's event->message reducer so a reloaded thread renders identically
(content, chronological blocks, tool calls, citations, artifacts, cards).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..db.supabase import get_db


def ensure_user_turn(
    session_id: str,
    content: str,
    asked_at: datetime,
    attached_doc_ids: list[str] | None = None,
) -> str | None:
    """Make sure the question that produced this answer is saved.

    The client saves the user turn fire-and-forget over the phone's own
    connection, while the answer is saved here on the server. When the phone's
    insert dropped, the thread showed an answer with no question above it and
    the person re-pasted their whole scenario (seen twice in one morning on
    11 September). Idempotent: if a user row with this content already exists
    in the session since shortly before the question was asked, nothing is
    written. Returns the inserted row id, or None when no repair was needed.
    """
    text = (content or "").strip()
    if not session_id or not text:
        return None
    db = get_db()
    since = (asked_at - timedelta(minutes=5)).isoformat()
    try:
        rows = (db.table("chat_messages").select("id,content")
                .eq("session_id", session_id).eq("role", "user")
                .gte("created_at", since).order("created_at", desc=True).limit(20)
                .execute().data or [])
    except Exception:  # noqa: BLE001 — a failed check must not block the answer's save
        return None
    if any((r.get("content") or "").strip() == text for r in rows):
        return None

    blocks = None
    if attached_doc_ids:
        try:
            docs = (db.table("legal_documents").select("id,title")
                    .in_("id", list(attached_doc_ids)).execute().data or [])
            if docs:
                blocks = [{"kind": "attachments",
                           "docs": [{"id": d["id"], "title": d.get("title") or "Document"} for d in docs]}]
        except Exception:  # noqa: BLE001
            blocks = None
    res = db.table("chat_messages").insert({
        "session_id": session_id,
        "role": "user",
        "content": text,
        "blocks": blocks,
        # Backdated to when the question arrived so it sorts above its answer.
        "created_at": asked_at.astimezone(timezone.utc).isoformat(),
    }).execute()
    try:
        return (res.data or [{}])[0].get("id")
    except Exception:  # noqa: BLE001
        return None


class RunAccumulator:
    """Folds the SSE event stream into the same row shape the frontend saves."""

    def __init__(self) -> None:
        self.content = ""
        self.blocks: list[dict] = []
        self.tool_calls: list[dict] = []
        self.citations: list[dict] = []
        self.web_sources: list[dict] = []
        self.artifacts: list[dict] = []
        self.compaction: dict | None = None
        # Which model actually produced this answer. Taken from the `done`
        # event rather than from config, because the agent rewrites it when a
        # fallback engages — if Sonnet rate-limits and Kimi answers, this must
        # say Kimi. Without it, answer feedback cannot be attributed to a
        # model and any A/B between tiers proves nothing.
        self.model: str | None = None

    def consume(self, e: dict) -> None:
        t = e.get("type")
        if t == "done" and e.get("model"):
            self.model = str(e["model"])
        if t == "token":
            chunk = e.get("content", "")
            self.content += chunk
            if self.blocks and self.blocks[-1].get("kind") == "text":
                self.blocks[-1]["text"] += chunk
            else:
                self.blocks.append({"kind": "text", "text": chunk})
        elif t == "tool_call":
            self.blocks.append({"kind": "tool", "toolCallId": e.get("id")})
            self.tool_calls.append({
                "id": e.get("id"), "name": e.get("name"),
                "input": e.get("input", {}), "status": "running", "db": [], "web": [],
            })
        elif t == "tool_result":
            for c in self.tool_calls:
                if c["id"] == e.get("id"):
                    c["status"] = "ok" if e.get("ok") else "error"
                    c["durationMs"] = e.get("ms")
                    c["db"] = e.get("db", [])
                    c["web"] = e.get("web", [])
        elif t == "ask_user":
            self.blocks.append({
                "kind": "ask_user",
                "id": e.get("id"),
                "question": e.get("question", ""),
                "options": e.get("options") or [],
                "allow_free_text": bool(e.get("allow_free_text", True)),
            })
        elif t == "citation_audit":
            # Persisted as a block so history reloads render the same verdicts
            # the live stream showed.
            self.blocks.append({"kind": "citation_audit",
                                "citations": e.get("citations") or []})
        elif t == "artifact":
            a = e.get("artifact")
            if a and not any(x.get("id") == a.get("id") for x in self.artifacts):
                self.artifacts.append(a)
        elif t == "compaction":
            self.compaction = {
                "summarised_messages": e.get("summarised_messages"),
                "tokens_before": e.get("tokens_before"),
                "tokens_after": e.get("tokens_after"),
            }
        elif t == "template_suggestion":
            self._upsert("templates", e.get("tool_call_id"),
                         {"kind": "templates", "toolCallId": e.get("tool_call_id"),
                          "templates": e.get("templates")})
        elif t == "application_plan":
            self._upsert("application_plan", e.get("tool_call_id"),
                         {"kind": "application_plan", "toolCallId": e.get("tool_call_id"),
                          "plan": e.get("plan")})
        elif t == "entitlement_breakdown":
            self._upsert("entitlement", e.get("tool_call_id"),
                         {"kind": "entitlement", "toolCallId": e.get("tool_call_id"),
                          "breakdown": e.get("breakdown")})
        elif t == "case_law":
            self._upsert("case_law", e.get("tool_call_id"),
                         {"kind": "case_law", "toolCallId": e.get("tool_call_id"),
                          "cases": e.get("cases")})
        elif t == "cheat_sheet":
            self._upsert("cheat_sheet", e.get("tool_call_id"),
                         {"kind": "cheat_sheet", "toolCallId": e.get("tool_call_id"),
                          "cheatSheet": e.get("cheat_sheet")})
        elif t == "quiz":
            self._upsert("quiz", e.get("tool_call_id"),
                         {"kind": "quiz", "toolCallId": e.get("tool_call_id"),
                          "quiz": e.get("quiz")})
        elif t == "sources":
            self.citations = e.get("db", [])
            self.web_sources = e.get("web", [])

    def _upsert(self, kind: str, tool_call_id, block: dict) -> None:
        for i, b in enumerate(self.blocks):
            if b.get("kind") == kind and b.get("toolCallId") == tool_call_id:
                self.blocks[i] = block
                return
        self.blocks.append(block)

    def has_content(self) -> bool:
        special = {"entitlement", "case_law", "application_plan", "templates",
                   "cheat_sheet", "quiz", "ask_user"}
        return bool(
            self.content.strip()
            or self.artifacts
            or any(b.get("kind") in special for b in self.blocks)
        )

    def save(self, session_id: str) -> str | None:
        """Persist the assembled assistant message. No-op if nothing meaningful.

        Returns the new row id so the caller can hand it to the client, which
        needs it to attach feedback to this answer without waiting for a
        reload — votes happen right after reading, or not at all.
        """
        if not self.has_content():
            return None
        res = get_db().table("chat_messages").insert({
            "session_id": session_id,
            "role": "assistant",
            "content": self.content,
            "blocks": self.blocks or None,
            "tool_calls": self.tool_calls or None,
            "citations": self.citations or None,
            "web_sources": self.web_sources or None,
            "artifacts": self.artifacts or None,
            "compaction": self.compaction,
            # Populated so message_feedback can be sliced by model. The columns
            # have existed since the initial schema but were never written.
            "model": self.model,
            "provider": ("moonshot" if (self.model or "").startswith("kimi")
                         else "anthropic" if self.model else None),
        }).execute()
        try:
            return (res.data or [{}])[0].get("id")
        except Exception:  # noqa: BLE001 — never fail a save over the return value
            return None
