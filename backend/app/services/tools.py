"""
Tool registry for the Levy agent.

Each tool has a JSON-Schema definition (sent to Claude) and an async handler
(executed when Claude emits a tool_use). Handlers return JSON-serialisable
dicts; the agent loop decides how to truncate before passing the result back
to the model.

Two source channels are surfaced:
  - "db" sources    — chunks from the ingested Zambian-law corpus (pgvector)
  - "web" sources   — pages from the open web, ideally on whitelisted .gov.zm
                      and institutional domains
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

from ..config import get_settings
from ..db.supabase import search_chunks
from .embedder import get_query_embedding


# ─── Curated source whitelist ────────────────────────────────────────────────
# These are the sites the model should prefer when answering Zambian-law
# questions. The list is intentionally narrow; the model can fall back to
# unrestricted web_search if nothing useful is found.
GOV_ZM_DOMAINS: list[str] = [
    "parliament.gov.zm",
    "lawsofzambia.com",
    "judiciaryzambia.com",
    "zambia.gov.zm",
    "moj.gov.zm",
    "pacra.org.zm",
    "minfin.gov.zm",
    "mlg.gov.zm",
    "zra.org.zm",
    "boz.zm",
    "eiti.org",
    "zmeiti.com",
    "pmrc.org.zm",
    "lazcouncil.org.zm",  # Law Association of Zambia
]


# ─── Tool definition ─────────────────────────────────────────────────────────


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., Awaitable[dict]]


@dataclass
class ToolCallRecord:
    """A single tool call as it happened during a run, kept for the UI/audit."""

    id: str
    name: str
    input: dict
    result: dict | None = None
    error: str | None = None
    duration_ms: int = 0
    db_sources: list[dict] = field(default_factory=list)
    web_sources: list[dict] = field(default_factory=list)


# ─── search_corpus ───────────────────────────────────────────────────────────


async def _search_corpus(query: str, top_k: int = 5, threshold: float | None = None) -> dict:
    """Vector search across the ingested Zambian-law corpus."""
    settings = get_settings()
    threshold = threshold if threshold is not None else settings.similarity_threshold
    embedding = await asyncio.to_thread(get_query_embedding, query)
    chunks = await asyncio.to_thread(search_chunks, embedding, top_k=top_k, threshold=threshold)

    results = []
    db_sources = []
    for c in chunks:
        meta = c.get("metadata") or {}
        act = meta.get("act_name") or "Unknown Act"
        section = meta.get("section_number") or ""
        part = meta.get("part_number") or ""
        results.append(
            {
                "chunk_id": c.get("id"),
                "act_name": act,
                "section": section,
                "part": part,
                "page_start": c.get("page_start"),
                "page_end": c.get("page_end"),
                "similarity": round(c.get("similarity", 0.0), 4),
                "content": c.get("content", ""),
            }
        )
        db_sources.append(
            {
                "id": c.get("id"),
                "act_name": act,
                "section": section,
                "part": part,
                "page_start": c.get("page_start"),
                "page_end": c.get("page_end"),
                "similarity": round(c.get("similarity", 0.0), 4),
                "content_preview": (c.get("content") or "")[:240],
            }
        )

    return {
        "result": {"matches": results, "count": len(results)},
        "db_sources": db_sources,
        "web_sources": [],
    }


# ─── Tavily-backed web tools ─────────────────────────────────────────────────


async def _tavily_search(
    query: str,
    *,
    max_results: int = 5,
    include_domains: list[str] | None = None,
) -> dict:
    settings = get_settings()
    if not settings.tavily_api_key:
        return {"result": {"error": "TAVILY_API_KEY not configured"}}

    payload: dict[str, Any] = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
        "include_answer": False,
        "include_raw_content": False,
    }
    if include_domains:
        payload["include_domains"] = include_domains

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post("https://api.tavily.com/search", json=payload)
        if resp.status_code != 200:
            return {"result": {"error": f"Tavily {resp.status_code}: {resp.text[:200]}"}}
        data = resp.json()

    results = []
    web_sources = []
    for r in data.get("results", []):
        url = r.get("url", "")
        title = r.get("title", "")
        content = r.get("content", "")
        score = r.get("score")
        results.append({"title": title, "url": url, "content": content, "score": score})
        web_sources.append(
            {
                "title": title,
                "url": url,
                "snippet": content[:300],
                "score": score,
                "domain": _extract_domain(url),
            }
        )

    return {
        "result": {"matches": results, "count": len(results)},
        "db_sources": [],
        "web_sources": web_sources,
    }


async def _gov_search(query: str, max_results: int = 5) -> dict:
    """Search restricted to whitelisted Zambian government / institutional sites."""
    return await _tavily_search(query, max_results=max_results, include_domains=GOV_ZM_DOMAINS)


async def _web_search(query: str, max_results: int = 5) -> dict:
    """General web search. Use only when gov_search returns nothing useful."""
    return await _tavily_search(query, max_results=max_results)


# ─── Web fetch (single URL, cleaned content) ─────────────────────────────────


async def _web_fetch(url: str) -> dict:
    """
    Fetch a URL and return cleaned text content. Uses Tavily's /extract endpoint
    (no separate readability dependency, avoids JS rendering needs).
    """
    settings = get_settings()
    if not settings.tavily_api_key:
        return {"result": {"error": "TAVILY_API_KEY not configured"}}

    payload = {"api_key": settings.tavily_api_key, "urls": [url]}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post("https://api.tavily.com/extract", json=payload)
        if resp.status_code != 200:
            return {"result": {"error": f"Tavily extract {resp.status_code}: {resp.text[:200]}"}}
        data = resp.json()

    items = data.get("results") or []
    if not items:
        return {"result": {"error": "no content extracted", "url": url}}
    item = items[0]
    raw = item.get("raw_content", "")
    return {
        "result": {"url": url, "content": raw, "length": len(raw)},
        "db_sources": [],
        "web_sources": [
            {
                "title": item.get("title") or url,
                "url": url,
                "snippet": raw[:300],
                "domain": _extract_domain(url),
            }
        ],
    }


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _extract_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


# ─── Registry ────────────────────────────────────────────────────────────────


def build_tool_registry(*, web_enabled: bool) -> dict[str, ToolDefinition]:
    """
    Build the set of tools available to the agent for a given turn.

    `search_corpus` is always available. The web tools are gated on the user
    toggling the "Search" affordance in the chat input; this keeps Tavily costs
    pinned to explicit user intent and avoids surprise web calls during
    pure-statute questions.
    """
    tools: dict[str, ToolDefinition] = {
        "search_corpus": ToolDefinition(
            name="search_corpus",
            description=(
                "Semantic search across the ingested Zambian-law corpus (Acts, "
                "regulations, statutes). Returns matching chunks with their Act "
                "name, section/part numbers, and source page numbers. Always "
                "prefer this over web search for statutory questions."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language query to search the corpus.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Max chunks to return (default 5, range 1-12).",
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Cosine similarity floor (0-1). Default 0.6.",
                    },
                },
                "required": ["query"],
            },
            handler=_search_corpus,
        ),
    }

    if web_enabled:
        tools["gov_search"] = ToolDefinition(
            name="gov_search",
            description=(
                "Web search restricted to official Zambian government and "
                "institutional websites (parliament.gov.zm, lawsofzambia.com, "
                "judiciaryzambia.com, pacra.org.zm, etc.). Use this for context "
                "the corpus does not contain — current procedures, fees, news, "
                "court judgments not yet ingested. Cite returned URLs back to "
                "the user."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "description": "Default 5, max 8."},
                },
                "required": ["query"],
            },
            handler=_gov_search,
        )
        tools["web_search"] = ToolDefinition(
            name="web_search",
            description=(
                "Unrestricted web search. Use only if gov_search returns no "
                "useful results. Lower-confidence sources; always cite URLs."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "description": "Default 5, max 8."},
                },
                "required": ["query"],
            },
            handler=_web_search,
        )
        tools["web_fetch"] = ToolDefinition(
            name="web_fetch",
            description=(
                "Fetch the full text of a single web URL. Use after web_search/"
                "gov_search when a result preview looks promising and you need "
                "the full page content to answer accurately."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Absolute http(s) URL."},
                },
                "required": ["url"],
            },
            handler=_web_fetch,
        )

    return tools


def to_anthropic_schema(registry: dict[str, ToolDefinition]) -> list[dict]:
    """Convert our internal registry into Anthropic's tool schema format."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        }
        for t in registry.values()
    ]


async def execute_tool(
    registry: dict[str, ToolDefinition],
    name: str,
    args: dict,
    *,
    timeout_seconds: int,
) -> dict:
    """Run a single tool with timeout, returning a normalized result envelope."""
    if name not in registry:
        return {"result": {"error": f"unknown tool: {name}"}}
    handler = registry[name].handler
    try:
        result = await asyncio.wait_for(handler(**args), timeout=timeout_seconds)
        if isinstance(result, dict) and "result" in result:
            return result
        return {"result": result, "db_sources": [], "web_sources": []}
    except asyncio.TimeoutError:
        return {
            "result": {"error": f"tool {name} timed out after {timeout_seconds}s"},
            "db_sources": [],
            "web_sources": [],
        }
    except Exception as e:  # noqa: BLE001
        return {
            "result": {"error": f"tool {name} raised {type(e).__name__}: {e}"},
            "db_sources": [],
            "web_sources": [],
        }


def truncate_for_model(payload: dict, max_chars: int) -> str:
    """Serialize a tool result for the model, truncating if oversized."""
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return text
    head = text[: max_chars - 80]
    return head + f' ... [truncated, original {len(text)} chars]'
