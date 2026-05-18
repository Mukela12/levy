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
from . import pdf_tools
from . import templates as templates_service


# ─── Curated source whitelist ────────────────────────────────────────────────
# These are the sites the model should prefer when answering Zambian-law
# questions. The list is intentionally narrow; the model can fall back to
# unrestricted web_search if nothing useful is found.
GOV_ZM_DOMAINS: list[str] = [
    # Legal & legislative
    "parliament.gov.zm",
    "lawsofzambia.com",
    "judiciaryzambia.com",
    "zambia.gov.zm",
    "moj.gov.zm",
    "pacra.org.zm",
    "lazcouncil.org.zm",  # Law Association of Zambia
    # Tax / finance / regulatory
    "minfin.gov.zm",
    "zra.org.zm",
    "boz.zm",
    # Devolved governance / local
    "mlg.gov.zm",
    # Economic / sectoral
    "eiti.org",
    "zmeiti.com",
    "pmrc.org.zm",
    # Procurement & infrastructure (validated set imported from
    # the Procura tender-intelligence pipeline; useful when answering
    # questions about public procurement law, supplier debarments, AWPs)
    "zppa.org.zm",
    "eprocure.zppa.org.zm",
    "rda.org.zm",
    "zesco.co.zm",
    # Statistics & digital governance
    "zamstats.gov.zm",
    "szi.gov.zm",
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


async def _search_corpus(
    query: str,
    top_k: int = 5,
    threshold: float | None = None,
    *,
    caller_user_id: str | None = None,
    attached_doc_ids: list[str] | None = None,
) -> dict:
    """Vector search across the ingested Zambian-law corpus, scoped by caller."""
    settings = get_settings()
    threshold = threshold if threshold is not None else settings.similarity_threshold
    embedding = await asyncio.to_thread(get_query_embedding, query)
    chunks = await asyncio.to_thread(
        search_chunks,
        embedding,
        top_k=top_k,
        threshold=threshold,
        caller_user_id=caller_user_id,
        attached_doc_ids=attached_doc_ids,
    )

    results = []
    db_sources = []
    for c in chunks:
        meta = c.get("metadata") or {}
        act = meta.get("act_name") or "Unknown Act"
        section = meta.get("section_number") or ""
        part = meta.get("part_number") or ""
        document_id = c.get("document_id")
        results.append(
            {
                "chunk_id": c.get("id"),
                "document_id": document_id,
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
                "document_id": document_id,
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


async def _web_crawl(start_url: str, max_pages: int = 4) -> dict:
    """
    Lightweight 1-hop crawl: fetches the start URL, extracts in-domain links,
    fetches up to `max_pages` of them, and returns concatenated content. Only
    follows links on the SAME domain as the start URL — keeps us safely
    inside government and institutional sites we whitelisted.
    """
    settings = get_settings()
    if not settings.tavily_api_key:
        return {"result": {"error": "TAVILY_API_KEY not configured"}}

    max_pages = max(1, min(int(max_pages or 4), 8))
    start_domain = _extract_domain(start_url)
    if not start_domain:
        return {"result": {"error": f"could not parse domain from {start_url}"}}

    pages: list[dict] = []
    web_sources: list[dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Fetch the seed page.
        resp = await client.post(
            "https://api.tavily.com/extract",
            json={"api_key": settings.tavily_api_key, "urls": [start_url]},
        )
        if resp.status_code != 200:
            return {"result": {"error": f"seed fetch {resp.status_code}: {resp.text[:200]}"}}
        items = (resp.json().get("results") or [])
        if not items:
            return {"result": {"error": f"seed page returned no content", "url": start_url}}
        seed = items[0]
        seed_content = seed.get("raw_content", "")
        pages.append({"url": start_url, "title": seed.get("title"), "content": seed_content})
        web_sources.append({
            "title": seed.get("title") or start_url, "url": start_url,
            "snippet": seed_content[:300], "domain": start_domain,
        })

        # Pull in-domain links from the seed content; cheap heuristic via regex.
        import re
        candidates: list[str] = []
        for m in re.finditer(r"https?://[^\s\"'<>]+", seed_content):
            u = m.group(0).rstrip(".,)\"'")
            if _extract_domain(u) == start_domain and u != start_url and u not in candidates:
                candidates.append(u)
            if len(candidates) >= max_pages:
                break

        # Fetch each follow-up.
        for follow_url in candidates[:max_pages]:
            try:
                r = await client.post(
                    "https://api.tavily.com/extract",
                    json={"api_key": settings.tavily_api_key, "urls": [follow_url]},
                )
                if r.status_code != 200:
                    continue
                its = r.json().get("results") or []
                if not its:
                    continue
                it = its[0]
                content = it.get("raw_content", "")
                pages.append({"url": follow_url, "title": it.get("title"), "content": content})
                web_sources.append({
                    "title": it.get("title") or follow_url, "url": follow_url,
                    "snippet": content[:300], "domain": start_domain,
                })
            except Exception:
                continue

    # Trim per-page content so the model doesn't drown — we keep the URLs and
    # the first ~3KB of each page, which is plenty for legal-context grounding.
    trimmed = []
    for p in pages:
        c = p["content"] or ""
        trimmed.append({
            "url": p["url"],
            "title": p.get("title"),
            "length": len(c),
            "content": c[:3000],
        })

    return {
        "result": {"start_url": start_url, "domain": start_domain, "pages": trimmed, "count": len(trimmed)},
        "db_sources": [],
        "web_sources": web_sources,
    }


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _extract_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


# ─── Registry ────────────────────────────────────────────────────────────────


def build_tool_registry(
    *,
    web_enabled: bool = True,
    owner_id: str | None = None,
    session_id: str | None = None,
    attached_doc_ids: list[str] | None = None,
) -> dict[str, ToolDefinition]:
    """
    Build the set of tools available to the agent for a given turn.

    Web tools (gov_search / web_search / web_fetch / web_crawl) are always
    registered now so the model can escalate to the open web on its own when
    the corpus comes up empty. The chat-input "Search" toggle remains useful
    as a HINT to the system prompt (when the user explicitly turns it on the
    agent prefers web sources earlier), but it no longer gates availability.

    `search_corpus` is always available. PDF artifact tools (extract /
    generate / merge / split / export brief) are also always available.
    """

    # Adapter: bind caller scope into search_corpus so the agent automatically
    # sees: global library + the user's uploads + this thread's attachments.
    async def _scoped_search(query, top_k=5, threshold=None):
        return await _search_corpus(
            query, top_k=top_k, threshold=threshold,
            caller_user_id=owner_id,
            attached_doc_ids=attached_doc_ids,
        )

    # Adapter: bind owner/session into PDF tool handlers so the agent doesn't
    # have to thread them in tool inputs.
    async def _extract(document_id, page_start, page_end, title=None):
        return await pdf_tools.pdf_extract_pages(
            document_id, int(page_start), int(page_end), title,
            owner_id=owner_id, session_id=session_id,
        )

    async def _generate(title, content_markdown, subtitle=None):
        return await pdf_tools.pdf_generate(
            title, content_markdown, subtitle,
            owner_id=owner_id, session_id=session_id,
        )

    async def _merge(parts, title):
        return await pdf_tools.pdf_merge(
            parts, title,
            owner_id=owner_id, session_id=session_id,
        )

    async def _split(ranges, artifact_id=None, document_id=None, title_prefix=None):
        return await pdf_tools.pdf_split(
            artifact_id=artifact_id,
            document_id=document_id,
            ranges=ranges,
            title_prefix=title_prefix,
            owner_id=owner_id, session_id=session_id,
        )

    async def _export_brief(title=None, include_appendix=True):
        if not session_id:
            return {"result": {"error": "export_thread_brief requires an active chat session"}}
        return await pdf_tools.export_thread_brief(
            session_id=session_id,
            title=title,
            include_appendix=include_appendix,
            owner_id=owner_id,
        )

    async def _suggest_templates(query: str | None = None):
        """Return up to 3 of the user's templates relevant to `query`."""
        if not owner_id:
            return {
                "result": {
                    "count": 0,
                    "templates": [],
                    "note": (
                        "Anonymous user — templates require sign-in. "
                        "Tell the user they can save reusable templates to "
                        "their account at /templates after signing in."
                    ),
                },
                "templates": [],
            }
        rows = await asyncio.to_thread(
            templates_service.suggest_templates_for, owner_id, query
        )
        compact = [
            {
                "id": r["id"],
                "name": r["name"],
                "description": r.get("description") or "",
                "file_type": r["file_type"],
                "page_count": r.get("page_count"),
                # Preview for the UI card (~2 lines worth of text).
                "preview": (r.get("preview_text") or "")[:240],
                # Full preview text the agent reads to draft from. Capped at
                # 1800 chars to keep tool-result payloads tight.
                "content": (r.get("preview_text") or "")[:1800],
            }
            for r in rows
        ]
        return {
            "result": {"count": len(compact), "templates": compact},
            "db_sources": [],
            "web_sources": [],
            # Surfaced separately by the agent loop so the UI can render
            # clickable suggestion cards inline in the chat.
            "templates": compact,
        }
    tools: dict[str, ToolDefinition] = {
        "pdf_extract_pages": ToolDefinition(
            name="pdf_extract_pages",
            description=(
                "Extract a contiguous page range from a corpus document and "
                "save it as a downloadable PDF artifact for the user. Use this "
                "when the user asks for 'sections X to Y' of an Act, or wants "
                "a focused excerpt to attach to something else. Get the "
                "document_id from a prior search_corpus result."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "UUID from search_corpus."},
                    "page_start": {"type": "integer", "description": "1-indexed inclusive."},
                    "page_end": {"type": "integer", "description": "1-indexed inclusive."},
                    "title": {"type": "string", "description": "Optional override for the artifact's title."},
                },
                "required": ["document_id", "page_start", "page_end"],
            },
            handler=_extract,
        ),
        "pdf_generate": ToolDefinition(
            name="pdf_generate",
            description=(
                "Render a polished PDF from Markdown. Use for legal memos, "
                "IRAC briefs, summaries, or any content the user wants to "
                "save / share. The output uses serif typography, A4 size, "
                "automatic page numbers. Inline citations like '[Companies "
                "Act, S.13] (p. 370)' render fine."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content_markdown": {
                        "type": "string",
                        "description": "Body content as Markdown (headings, lists, tables, blockquotes all supported).",
                    },
                    "subtitle": {
                        "type": "string",
                        "description": "Optional grey subtitle line under the heading (e.g. matter name, date).",
                    },
                },
                "required": ["title", "content_markdown"],
            },
            handler=_generate,
        ),
        "pdf_split": ToolDefinition(
            name="pdf_split",
            description=(
                "Split a PDF (a corpus document or an existing artifact) into "
                "smaller PDFs by page ranges. Each range yields its own "
                "artifact card. Use when the user asks for several focused "
                "excerpts at once, e.g. 'give me sections 1-5, 12-18, and "
                "30-34 of the Companies Act as separate PDFs'."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "Source corpus document UUID."},
                    "artifact_id": {"type": "string", "description": "OR — split an existing artifact instead."},
                    "title_prefix": {"type": "string", "description": "Prefix for auto-generated piece titles."},
                    "ranges": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "page_start": {"type": "integer"},
                                "page_end": {"type": "integer"},
                                "title": {"type": "string"},
                            },
                            "required": ["page_start", "page_end"],
                        },
                    },
                },
                "required": ["ranges"],
            },
            handler=_split,
        ),
        "export_thread_brief": ToolDefinition(
            name="export_thread_brief",
            description=(
                "Compile the entire conversation into a single polished PDF "
                "brief, with an appendix that includes the cited page ranges "
                "from every corpus document referenced. Use when the user "
                "asks to 'export this thread' / 'turn this into a brief' / "
                "'save the consultation as a PDF'. Always preferable to "
                "manually re-running pdf_generate."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Optional title; defaults to the session title."},
                    "include_appendix": {
                        "type": "boolean",
                        "description": "Default true. Set false for a compact prose-only brief.",
                    },
                },
            },
            handler=_export_brief,
        ),
        "pdf_merge": ToolDefinition(
            name="pdf_merge",
            description=(
                "Concatenate multiple PDFs (existing artifacts and/or page "
                "ranges from corpus documents) into a single new artifact. "
                "Useful for assembling appendices: e.g. 'merge my generated "
                "memo with sections 5-10 of the Companies Act'. Each part "
                "must specify EITHER artifact_id OR document_id; if "
                "document_id is given without page_start/page_end, the whole "
                "document is included."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "parts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "artifact_id": {"type": "string"},
                                "document_id": {"type": "string"},
                                "page_start": {"type": "integer"},
                                "page_end": {"type": "integer"},
                            },
                        },
                    },
                },
                "required": ["title", "parts"],
            },
            handler=_merge,
        ),
        "suggest_templates": ToolDefinition(
            name="suggest_templates",
            description=(
                "List up to 3 of the user's saved document templates that look "
                "relevant to a drafting request. Use this BEFORE pdf_generate "
                "or any other artifact tool when the user asks you to draft, "
                "write, or prepare any document (memo, contract, NDA, demand "
                "letter, brief, etc.) — even if they didn't mention templates "
                "explicitly. The UI shows the returned templates as clickable "
                "cards. If the user already named a specific template, pass "
                "that as the `query`. The tool returns a `templates` array; "
                "if it's empty, the user has no templates and you should "
                "proceed normally with pdf_generate."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Free-text describing what the user wants to draft "
                            "(e.g. 'employment offer letter', 'NDA'). Used to "
                            "rank the user's templates by keyword relevance."
                        ),
                    },
                },
            },
            handler=_suggest_templates,
        ),
        "search_corpus": ToolDefinition(
            name="search_corpus",
            description=(
                "Semantic search across the legal corpus visible to this user: "
                "the curated global library of Zambian Acts + the user's own "
                "uploaded documents + any documents attached to this chat "
                "thread. Returns matching chunks with their Act name, section/"
                "part numbers, and source page numbers. Always prefer this "
                "over web search for statutory questions."
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
            handler=_scoped_search,
        ),
    }

    # Web tools — always registered. The agent decides when to use them.
    _ = web_enabled  # kept for backwards compat with the kwarg
    if True:
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
        tools["web_crawl"] = ToolDefinition(
            name="web_crawl",
            description=(
                "Fetch a starting URL and follow up to N in-domain links from "
                "it (1 hop, same hostname only). Use when one gov page hints "
                "the answer is split across linked subpages — e.g. PACRA's "
                "fees+forms hub or parliament.gov.zm act indexes. Returns "
                "trimmed text from each page."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "start_url": {"type": "string"},
                    "max_pages": {
                        "type": "integer",
                        "description": "Default 4, max 8. Includes the seed page.",
                    },
                },
                "required": ["start_url"],
            },
            handler=_web_crawl,
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
