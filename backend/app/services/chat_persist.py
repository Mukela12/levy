"""Server-side accumulation + durable persistence of an agent run.

Tier-1 durable execution: the agent run is driven in a detached task so it
completes and saves the assistant message even when the client disconnects
(closed tab, locked phone, dropped mobile signal). This accumulator mirrors
the frontend's event->message reducer so a reloaded thread renders identically
(content, chronological blocks, tool calls, citations, artifacts, cards).
"""
from __future__ import annotations

from ..db.supabase import get_db


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

    def consume(self, e: dict) -> None:
        t = e.get("type")
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
                   "cheat_sheet", "quiz"}
        return bool(
            self.content.strip()
            or self.artifacts
            or any(b.get("kind") in special for b in self.blocks)
        )

    def save(self, session_id: str) -> None:
        """Persist the assembled assistant message. No-op if nothing meaningful."""
        if not self.has_content():
            return
        get_db().table("chat_messages").insert({
            "session_id": session_id,
            "role": "assistant",
            "content": self.content,
            "blocks": self.blocks or None,
            "tool_calls": self.tool_calls or None,
            "citations": self.citations or None,
            "web_sources": self.web_sources or None,
            "artifacts": self.artifacts or None,
            "compaction": self.compaction,
        }).execute()
