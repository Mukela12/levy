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
import re
import warnings
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

# Several Zambian gov hosts serve incomplete cert chains. We catch the
# verify-disabled fallback case in _web_fetch — mute the per-request
# urllib3 warning so the agent log stays readable.
warnings.filterwarnings("ignore", message="Unverified HTTPS request")
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

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
    Fetch a URL and return cleaned text content.

    First tries Tavily's /extract endpoint (fast, handles JS rendering and
    delivers cleaned text). When Tavily can't reach the host — common on
    Zambian gov sites that ship a broken cert chain — falls back to a
    direct httpx fetch with verify=False, strips HTML to plain text, and
    returns that instead. Without the fallback the agent ends up reporting
    "no content extracted" for half the gov sources and gives up.
    """
    settings = get_settings()

    tavily_error: str | None = None
    if settings.tavily_api_key:
        try:
            payload = {"api_key": settings.tavily_api_key, "urls": [url]}
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.tavily.com/extract", json=payload
                )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("results") or []
                if items:
                    item = items[0]
                    raw = item.get("raw_content", "")
                    if raw.strip():
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
                # Tavily returned 200 but no usable content — record the
                # failure reason if any so we can include it in the final
                # error when the fallback also fails.
                failed = (data.get("failed_results") or [{}])[0]
                tavily_error = failed.get("error") or "no content extracted"
            else:
                tavily_error = f"Tavily extract {resp.status_code}: {resp.text[:120]}"
        except Exception as e:  # noqa: BLE001
            tavily_error = f"Tavily extract exception: {e}"

    # Direct-fetch fallback. Several Zambian gov hosts (parliament.gov.zm
    # in particular) serve an incomplete certificate chain that public
    # extraction APIs reject; we accept the cert because the content is
    # a public web page either way.
    direct_error: str | None = None
    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            verify=False,
            headers={"User-Agent": "Mozilla/5.0 LevyFetch/1.0"},
        ) as client:
            dr = await client.get(url)
        if dr.status_code != 200:
            direct_error = f"direct fetch {dr.status_code}"
        else:
            text = _html_to_text(dr.text)
            if text.strip():
                return {
                    "result": {
                        "url": url,
                        "content": text,
                        "length": len(text),
                        "fallback": "direct",
                    },
                    "db_sources": [],
                    "web_sources": [
                        {
                            "title": _extract_html_title(dr.text) or url,
                            "url": url,
                            "snippet": text[:300],
                            "domain": _extract_domain(url),
                        }
                    ],
                }
            direct_error = "direct fetch returned empty page"
    except Exception as e:  # noqa: BLE001
        direct_error = f"direct fetch exception: {e}"

    return {
        "result": {
            "error": " | ".join(filter(None, [tavily_error, direct_error]))
            or "could not fetch",
            "url": url,
        }
    }


def _html_to_text(html: str) -> str:
    """Strip script/style + tags from a raw HTML page and collapse whitespace.

    Best-effort regex pass — we don't ship BeautifulSoup just for this.
    For Zambian gov pages (mostly Drupal / WordPress server-rendered HTML)
    the result is more than enough to feed to the model.
    """
    if not html:
        return ""
    # Drop script + style blocks entirely.
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.S | re.I)
    # Decode common entities cheaply.
    html = (
        html.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    # Block-level tags → newlines (keeps paragraph structure for the model).
    html = re.sub(r"</?(p|div|br|li|h\d|tr|td|th)[^>]*>", "\n", html, flags=re.I)
    # Strip any remaining tags.
    text = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace.
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:12000]  # plenty for the model; trim runaway pages


def _extract_html_title(html: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", html or "", flags=re.S | re.I)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).strip() or None


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
    def _fetch_template(template_id: str | None) -> dict | None:
        """Look up a user-owned template, swallowing errors so a missing or
        cross-owner template just gracefully falls back to the default
        format rather than failing the draft."""
        if not template_id or not owner_id:
            return None
        try:
            return templates_service.get_template_by_id(owner_id, template_id)
        except Exception:  # noqa: BLE001
            return None

    async def _draft_summons(
        procedural_mode: str,
        court_division: str,
        applicant_name: str,
        respondent_name: str,
        reliefs: list[str],
        urgency: str = "inter_partes",
        cause_of_action: str | None = None,
        cause_number: str | None = None,
        statutory_basis: list[str] | None = None,
        supporting_deponent: str | None = None,
        counsel_name: str | None = None,
        counsel_firm: str | None = None,
        applicant_address: str | None = None,
        respondent_address: str | None = None,
        return_date_note: str | None = None,
        template_id: str | None = None,
    ):
        """Draft the originating process (Summons / Notice of Motion / etc.)
        for a Zambian court application and store it as a PDF artifact.

        Follows the standard heading + parties block, then the document-type
        recital, then the numbered reliefs, then the cross-reference to the
        Affidavit in Support and Skeletal Arguments, then the date / signature
        block / address for service."""
        from datetime import datetime

        mode = (procedural_mode or "").strip()
        applicant = (applicant_name or "").strip()
        respondent = (respondent_name or "").strip()
        cleaned_reliefs = [r.strip() for r in (reliefs or []) if r and r.strip()]

        if not mode:
            return {"result": {"error": "procedural_mode required"}}
        if not applicant:
            return {"result": {"error": "applicant_name required"}}
        if not respondent:
            return {"result": {"error": "respondent_name required"}}
        if not cleaned_reliefs:
            return {"result": {"error": "reliefs must be a non-empty list"}}

        is_ex_parte = (urgency or "").strip().lower() == "ex_parte" or "ex parte" in mode.lower()

        # Determine party-role labels for the parties block. Originating
        # Summons in Zambia uses Plaintiff/Defendant; Notice of Motion uses
        # Applicant/Respondent; Petition uses Petitioner/Respondent.
        mode_lower = mode.lower()
        if "petition" in mode_lower:
            applicant_role, respondent_role = "PETITIONER", "RESPONDENT"
        elif "writ" in mode_lower or "statement of claim" in mode_lower:
            applicant_role, respondent_role = "PLAINTIFF", "DEFENDANT"
        elif "originating summons" in mode_lower:
            applicant_role, respondent_role = "PLAINTIFF", "DEFENDANT"
        else:
            applicant_role, respondent_role = "APPLICANT", "RESPONDENT"

        heading_html = pdf_tools.render_court_heading(
            court_division=court_division,
            cause_number=cause_number,
            applicant_name=applicant,
            respondent_name=respondent,
            applicant_role=applicant_role,
            respondent_role=respondent_role,
        )

        # Document-type recital: the wording differs by procedural mode.
        title_line = f'<div class="doc-title">{mode.upper()}</div>'

        pursuant_line = ""
        if statutory_basis:
            joined = "; ".join(s.strip() for s in statutory_basis if s and s.strip())
            if joined:
                pursuant_line = (
                    f'<p style="text-align:center; font-style:italic;">'
                    f'(Pursuant to {joined})'
                    f'</p>'
                )

        ex_parte_phrase = "EX PARTE " if is_ex_parte else ""
        return_phrase = (
            return_date_note.strip()
            if return_date_note and return_date_note.strip()
            else "on a date to be appointed by the Honourable Court"
        )

        if "originating summons" in mode_lower:
            opening_recital = (
                f'<p class="recital">'
                f'LET <strong>{respondent}</strong> '
                f'of <em>{respondent_address or "[address for service]"}</em>, '
                f'within fourteen (14) days after the service of this Summons on you, '
                f'inclusive of the day of such service, cause an appearance to be entered '
                f'on your behalf to this Summons, which is issued at the suit of '
                f'<strong>{applicant}</strong>, the Applicant herein, '
                f'who seeks the following orders:'
                f'</p>'
            )
        elif "petition" in mode_lower:
            opening_recital = (
                f'<p class="recital">'
                f'The Petition of <strong>{applicant}</strong> respectfully showeth that '
                f'the Petitioner seeks the following orders against '
                f'<strong>{respondent}</strong>:'
                f'</p>'
            )
        else:
            opening_recital = (
                f'<p class="recital">'
                f'TAKE NOTICE that {return_phrase}, '
                f'Counsel for the {applicant_role.capitalize()} will {ex_parte_phrase}'
                f'move this Honourable Court for the following orders:'
                f'</p>'
            )

        reliefs_html = (
            "<ol>"
            + "".join(f"<li>{r}</li>" for r in cleaned_reliefs)
            + "</ol>"
        )

        # Cross-reference to supporting documents.
        deponent = (supporting_deponent or applicant).strip()
        if "originating summons" in mode_lower or "petition" in mode_lower:
            support_clause = (
                f'<p>This {mode} is supported by the Affidavit of <strong>{deponent}</strong> '
                f'sworn and filed herewith, together with Skeletal Arguments in support.</p>'
            )
        else:
            support_clause = (
                f'<p>AND TAKE FURTHER NOTICE that this application is supported by '
                f'the Affidavit of <strong>{deponent}</strong> sworn and filed herewith, '
                f'together with Skeletal Arguments in support of the application.</p>'
            )

        today = datetime.utcnow().strftime("%d{suffix} day of %B, %Y")
        # crude ordinal — not life-critical, the law firm normally fills the
        # day at filing anyway.
        day = datetime.utcnow().day
        if 10 <= day % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        dated_line = (
            f'<p class="dated">DATED at {{city}} this {today.format(suffix=suffix)}.</p>'
        ).format(city=(applicant_address or "Lusaka"))

        signature_block = (
            '<div class="sig-line"></div>'
            f'<p><strong>{(counsel_name or "[COUNSEL NAME]").upper()}</strong><br/>'
            f'{counsel_firm or "[FIRM NAME / CHAMBERS]"}<br/>'
            f'Counsel for the {applicant_role.capitalize()}</p>'
        )

        # Address for service: required for inter partes filings.
        if not is_ex_parte:
            served = (
                '<div class="served">'
                '<p><strong>To:</strong><br/>'
                'The Registrar<br/>'
                'High Court of Zambia<br/>'
                'Lusaka, Zambia</p>'
                '<p><strong>AND TO:</strong><br/>'
                f'{respondent}<br/>'
                f'{respondent_address or "[address for service]"}</p>'
                '</div>'
            )
        else:
            served = (
                '<div class="served">'
                '<p><strong>To:</strong><br/>'
                'The Registrar<br/>'
                'High Court of Zambia<br/>'
                'Lusaka, Zambia</p>'
                '<p><em>(Ex parte application — service on the Respondent dispensed with pending the leave of the Court.)</em></p>'
                '</div>'
            )

        template = _fetch_template(template_id)
        letterhead = pdf_tools.render_template_letterhead(template)

        body_md = "\n\n".join([
            letterhead,
            heading_html,
            title_line,
            pursuant_line,
            opening_recital,
            reliefs_html,
            support_clause,
            dated_line,
            signature_block,
            served,
        ])

        artifact_title = (
            f"{mode} — {applicant} v {respondent}"
            if len(applicant) < 30 and len(respondent) < 30
            else mode
        )

        return await pdf_tools.pdf_generate_legal(
            title=artifact_title,
            body_markdown=body_md,
            meta_tool="draft_summons",
            owner_id=owner_id,
            session_id=session_id,
        )

    async def _draft_affidavit(
        procedural_mode: str,
        court_division: str,
        applicant_name: str,
        respondent_name: str,
        deponent_name: str,
        deponent_address: str,
        deponent_occupation: str,
        facts: list[str],
        deponent_role: str = "Applicant",
        deponent_gender: str = "adult",
        supporting_document: str | None = None,
        cause_number: str | None = None,
        exhibits: list[dict] | None = None,
        commissioner_name: str | None = None,
        sworn_at_city: str | None = None,
        template_id: str | None = None,
    ):
        """Draft an Affidavit in Support and store as a PDF artifact.

        Uses the same Zambian court caption as the summons, then the standard
        deposition opening, then numbered THAT-statements (one per `facts`
        item), then the swear-clause + Commissioner for Oaths block, then an
        exhibits index if any are supplied.
        """
        from datetime import datetime

        mode = (procedural_mode or "").strip()
        applicant = (applicant_name or "").strip()
        respondent = (respondent_name or "").strip()
        deponent = (deponent_name or "").strip()
        cleaned_facts = [f.strip() for f in (facts or []) if f and f.strip()]
        cleaned_exhibits = [
            {
                "label": (e.get("label") or "").strip(),
                "description": (e.get("description") or "").strip(),
            }
            for e in (exhibits or [])
            if e and (e.get("label") or e.get("description"))
        ]

        if not mode:
            return {"result": {"error": "procedural_mode required"}}
        if not deponent:
            return {"result": {"error": "deponent_name required"}}
        if not (deponent_address or "").strip():
            return {"result": {"error": "deponent_address required"}}
        if not (deponent_occupation or "").strip():
            return {"result": {"error": "deponent_occupation required"}}
        if not cleaned_facts:
            return {"result": {"error": "facts must be a non-empty list"}}

        mode_lower = mode.lower()
        if "petition" in mode_lower:
            applicant_role, respondent_role = "PETITIONER", "RESPONDENT"
        elif "writ" in mode_lower or "originating summons" in mode_lower:
            applicant_role, respondent_role = "PLAINTIFF", "DEFENDANT"
        else:
            applicant_role, respondent_role = "APPLICANT", "RESPONDENT"

        heading_html = pdf_tools.render_court_heading(
            court_division=court_division,
            cause_number=cause_number,
            applicant_name=applicant or "[APPLICANT NAME]",
            respondent_name=respondent or "[RESPONDENT NAME]",
            applicant_role=applicant_role,
            respondent_role=respondent_role,
        )

        support_doc = (supporting_document or mode).strip()
        doc_title = f'<div class="doc-title">AFFIDAVIT IN SUPPORT OF {support_doc.upper()}</div>'

        gender_phrase = (deponent_gender or "adult").strip()
        # Allow either a bare gender word ("male", "female") or a pre-composed
        # phrase like "adult Zambian male of full legal capacity".
        if gender_phrase.lower() in {"male", "female"}:
            gender_phrase = f"adult Zambian {gender_phrase.lower()}"
        gender_article = "an" if gender_phrase[:1].lower() in {"a", "e", "i", "o", "u"} else "a"

        deposition_opening = (
            f'<p class="recital">'
            f'I, <strong>{deponent.upper()}</strong>, '
            f'of <em>{deponent_address}</em>, '
            f'in the Republic of Zambia, '
            f'{gender_article} {gender_phrase} of full legal capacity, '
            f'{deponent_occupation}, '
            f'do solemnly and sincerely make oath and state as follows:'
            f'</p>'
        )

        # The first numbered paragraph is canonical: identifies the deponent
        # and the source of their knowledge. We prepend it automatically so
        # the agent doesn't have to remember.
        role = (deponent_role or "Applicant").strip()
        first_para = (
            f"THAT I am the {role} in this matter and the facts deposed to "
            f"herein are within my personal knowledge save where stated "
            f"otherwise to be true to the best of my knowledge, information "
            f"and belief."
        )
        all_facts = [first_para] + cleaned_facts + [
            f"THAT I make this Affidavit in support of the {support_doc} "
            f"filed herewith and I verily pray that this Honourable Court "
            f"may be pleased to grant the orders sought therein."
        ]

        # Ensure each fact starts with "THAT " in caps for the Zambian style.
        def _that(text: str) -> str:
            t = text.lstrip()
            if not t.upper().startswith("THAT"):
                t = "THAT " + t
            # Add trailing period if missing.
            if not t.rstrip().endswith((".", "?", "!")):
                t = t.rstrip() + "."
            return t

        facts_html = (
            "<ol>"
            + "".join(f"<li>{_that(f)}</li>" for f in all_facts)
            + "</ol>"
        )

        sworn_city = (sworn_at_city or "Lusaka").strip()
        day = datetime.utcnow().day
        if 10 <= day % 100 <= 20:
            ord_suffix = "th"
        else:
            ord_suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        today = datetime.utcnow().strftime(f"%-d{ord_suffix} day of %B, %Y")

        jurat = (
            f'<p class="dated">SWORN at <strong>{sworn_city}</strong> '
            f'this {today}.</p>'
            '<div class="sig-line"></div>'
            f'<p><strong>{deponent.upper()}</strong><br/>(DEPONENT)</p>'
            '<p class="dated"><strong>BEFORE ME:</strong></p>'
            '<div class="sig-line"></div>'
            f'<p><strong>{(commissioner_name or "[COMMISSIONER FOR OATHS]").upper()}</strong><br/>'
            'COMMISSIONER FOR OATHS</p>'
        )

        exhibits_html = ""
        if cleaned_exhibits:
            rows = "".join(
                f'<tr><td><strong>"{e["label"] or "MB" + str(i+1)}"</strong></td>'
                f'<td>{e["description"]}</td></tr>'
                for i, e in enumerate(cleaned_exhibits)
            )
            exhibits_html = (
                '<div class="doc-title" style="font-size:11pt;text-decoration:none;margin-top:20pt;">EXHIBITS</div>'
                '<table style="width:100%;">'
                + rows
                + '</table>'
            )

        template = _fetch_template(template_id)
        letterhead = pdf_tools.render_template_letterhead(template)

        body_md = "\n\n".join([
            letterhead,
            heading_html,
            doc_title,
            deposition_opening,
            facts_html,
            jurat,
            exhibits_html,
        ])

        artifact_title = (
            f"Affidavit in Support — {applicant or deponent} v {respondent}"
            if respondent and len(applicant or deponent) < 30 and len(respondent) < 30
            else f"Affidavit in Support — {deponent}"
        )

        return await pdf_tools.pdf_generate_legal(
            title=artifact_title,
            body_markdown=body_md,
            meta_tool="draft_affidavit",
            owner_id=owner_id,
            session_id=session_id,
        )

    async def _draft_skeletal(
        procedural_mode: str,
        court_division: str,
        applicant_name: str,
        respondent_name: str,
        introduction: str,
        issues: list[str],
        submissions: list[dict],
        prayer: str,
        supporting_document: str | None = None,
        cause_number: str | None = None,
        authorities_cases: list[str] | None = None,
        authorities_statutes: list[str] | None = None,
        counsel_name: str | None = None,
        counsel_firm: str | None = None,
        template_id: str | None = None,
    ):
        """Draft Skeletal Arguments in support of an application.

        Renders the IRAC-style structure Zambian counsel use: Introduction →
        Issues for Determination → Submissions (one per issue, with
        authorities woven in) → Prayer → List of Authorities → signature.
        """
        mode = (procedural_mode or "").strip()
        applicant = (applicant_name or "").strip()
        respondent = (respondent_name or "").strip()
        cleaned_issues = [i.strip() for i in (issues or []) if i and i.strip()]
        cleaned_subs = [
            {
                "title": (s.get("title") or "").strip(),
                "paragraphs": [p.strip() for p in (s.get("paragraphs") or []) if p and p.strip()],
                "citations": [c.strip() for c in (s.get("citations") or []) if c and c.strip()],
            }
            for s in (submissions or [])
            if s
        ]
        cases = [c.strip() for c in (authorities_cases or []) if c and c.strip()]
        statutes = [s.strip() for s in (authorities_statutes or []) if s and s.strip()]

        if not mode:
            return {"result": {"error": "procedural_mode required"}}
        if not introduction or not introduction.strip():
            return {"result": {"error": "introduction required"}}
        if not cleaned_issues:
            return {"result": {"error": "issues must be a non-empty list"}}
        if not cleaned_subs:
            return {"result": {"error": "submissions must be a non-empty list"}}
        if not prayer or not prayer.strip():
            return {"result": {"error": "prayer required"}}

        mode_lower = mode.lower()
        if "petition" in mode_lower:
            applicant_role, respondent_role = "PETITIONER", "RESPONDENT"
        elif "writ" in mode_lower or "originating summons" in mode_lower:
            applicant_role, respondent_role = "PLAINTIFF", "DEFENDANT"
        else:
            applicant_role, respondent_role = "APPLICANT", "RESPONDENT"

        heading_html = pdf_tools.render_court_heading(
            court_division=court_division,
            cause_number=cause_number,
            applicant_name=applicant or "[APPLICANT NAME]",
            respondent_name=respondent or "[RESPONDENT NAME]",
            applicant_role=applicant_role,
            respondent_role=respondent_role,
        )

        support_doc = (supporting_document or mode).strip()
        doc_title = (
            f'<div class="doc-title">SKELETAL ARGUMENTS IN SUPPORT OF '
            f'{support_doc.upper()}</div>'
        )

        # 1.0 Introduction
        intro_paragraphs = [
            f'<p>{p}</p>'
            for p in introduction.strip().split("\n\n")
            if p.strip()
        ]
        intro_section = (
            '<h2 style="text-align:left;letter-spacing:0;font-size:12pt;'
            'margin-top:14pt;">1.0 INTRODUCTION</h2>'
            + "".join(
                f'<p><strong>1.{i+1}</strong> {p[3:-4] if p.startswith("<p>") and p.endswith("</p>") else p}</p>'
                for i, p in enumerate(intro_paragraphs)
            )
        )

        # 2.0 Issues for Determination
        issues_section = (
            '<h2 style="text-align:left;letter-spacing:0;font-size:12pt;'
            'margin-top:14pt;">2.0 ISSUES FOR DETERMINATION</h2>'
            + "".join(
                f'<p><strong>2.{i+1}</strong> {issue}</p>'
                for i, issue in enumerate(cleaned_issues)
            )
        )

        # 3.0 Submissions — one block per submission item.
        sub_blocks = []
        for s_idx, sub in enumerate(cleaned_subs):
            title = sub["title"] or f"Submission on Issue {s_idx + 1}"
            sub_blocks.append(
                f'<h3 style="text-align:left;font-size:11.5pt;margin-top:12pt;">'
                f'3.{s_idx + 1} {title}</h3>'
            )
            for p_idx, para in enumerate(sub["paragraphs"]):
                sub_blocks.append(
                    f'<p><strong>3.{s_idx + 1}.{p_idx + 1}</strong> {para}</p>'
                )
            if sub["citations"]:
                cites = "; ".join(sub["citations"])
                sub_blocks.append(
                    f'<p style="font-style:italic;margin-left:18pt;">'
                    f'Authority: {cites}</p>'
                )
        submissions_section = (
            '<h2 style="text-align:left;letter-spacing:0;font-size:12pt;'
            'margin-top:14pt;">3.0 SUBMISSIONS</h2>'
            + "".join(sub_blocks)
        )

        # 4.0 Prayer
        prayer_section = (
            '<h2 style="text-align:left;letter-spacing:0;font-size:12pt;'
            'margin-top:14pt;">4.0 PRAYER</h2>'
            f'<p><strong>4.1</strong> {prayer.strip()}</p>'
        )

        # List of Authorities
        authorities_section_parts = []
        if cases or statutes:
            authorities_section_parts.append(
                '<h2 style="text-align:left;letter-spacing:0;font-size:12pt;'
                'margin-top:14pt;">LIST OF AUTHORITIES</h2>'
            )
        if cases:
            authorities_section_parts.append(
                '<p style="margin-bottom:4pt;"><strong>Cases:</strong></p>'
            )
            authorities_section_parts.append(
                "<ol>" + "".join(f"<li>{c}</li>" for c in cases) + "</ol>"
            )
        if statutes:
            authorities_section_parts.append(
                '<p style="margin-bottom:4pt;"><strong>Statutes & Rules:</strong></p>'
            )
            authorities_section_parts.append(
                "<ol>" + "".join(f"<li>{s}</li>" for s in statutes) + "</ol>"
            )
        authorities_section = "".join(authorities_section_parts)

        # Signature
        signature = (
            '<div class="sig-line"></div>'
            f'<p><strong>{(counsel_name or "[COUNSEL NAME]").upper()}</strong><br/>'
            f'{counsel_firm or "[FIRM NAME / CHAMBERS]"}<br/>'
            f'Counsel for the {applicant_role.capitalize()}</p>'
        )

        template = _fetch_template(template_id)
        letterhead = pdf_tools.render_template_letterhead(template)

        body_md = "\n\n".join([
            letterhead,
            heading_html,
            doc_title,
            intro_section,
            issues_section,
            submissions_section,
            prayer_section,
            authorities_section,
            signature,
        ])

        artifact_title = (
            f"Skeletal Arguments — {applicant} v {respondent}"
            if respondent and len(applicant) < 30 and len(respondent) < 30
            else "Skeletal Arguments"
        )

        return await pdf_tools.pdf_generate_legal(
            title=artifact_title,
            body_markdown=body_md,
            meta_tool="draft_skeletal",
            owner_id=owner_id,
            session_id=session_id,
        )

    async def _draft_order(
        procedural_mode: str,
        court_division: str,
        applicant_name: str,
        respondent_name: str,
        orders: list[str],
        urgency: str = "inter_partes",
        cause_number: str | None = None,
        supporting_deponent: str | None = None,
        costs_direction: str | None = None,
        counsel_name: str | None = None,
        counsel_firm: str | None = None,
        firm_address: str | None = None,
        template_id: str | None = None,
    ):
        """Draft a Draft Order for endorsement and save as PDF artifact.

        Standard form: UPON-recital → IT IS HEREBY ORDERED THAT → numbered
        orders → costs direction → DATED line → JUDGE signature line →
        Drawn by chambers block.
        """
        mode = (procedural_mode or "").strip()
        applicant = (applicant_name or "").strip()
        respondent = (respondent_name or "").strip()
        cleaned_orders = [o.strip() for o in (orders or []) if o and o.strip()]

        if not mode:
            return {"result": {"error": "procedural_mode required"}}
        if not applicant:
            return {"result": {"error": "applicant_name required"}}
        if not respondent:
            return {"result": {"error": "respondent_name required"}}
        if not cleaned_orders:
            return {"result": {"error": "orders must be a non-empty list"}}

        is_ex_parte = (urgency or "").strip().lower() == "ex_parte" or "ex parte" in mode.lower()
        mode_lower = mode.lower()
        if "petition" in mode_lower:
            applicant_role, respondent_role = "PETITIONER", "RESPONDENT"
        elif "writ" in mode_lower or "originating summons" in mode_lower:
            applicant_role, respondent_role = "PLAINTIFF", "DEFENDANT"
        else:
            applicant_role, respondent_role = "APPLICANT", "RESPONDENT"

        heading_html = pdf_tools.render_court_heading(
            court_division=court_division,
            cause_number=cause_number,
            applicant_name=applicant,
            respondent_name=respondent,
            applicant_role=applicant_role,
            respondent_role=respondent_role,
        )

        doc_title = '<div class="doc-title">DRAFT ORDER</div>'

        deponent = (supporting_deponent or applicant).strip()
        if is_ex_parte:
            hearing_clause = (
                f"AND UPON hearing Counsel for the {applicant_role.capitalize()} ex parte"
            )
        else:
            hearing_clause = (
                f"AND UPON hearing Counsel for the {applicant_role.capitalize()} "
                f"and Counsel for the {respondent_role.capitalize()} (or no appearance entered)"
            )
        upon_recital = (
            f'<p class="recital">'
            f'UPON the application by way of {mode} filed by the '
            f'{applicant_role.capitalize()} herein '
            f'AND UPON reading the Affidavit in Support sworn by '
            f'<strong>{deponent}</strong> together with the Skeletal Arguments '
            f'filed herewith {hearing_clause}:'
            f'</p>'
        )

        ordered_heading = (
            '<p style="text-align:center;font-weight:700;letter-spacing:1pt;'
            'text-transform:uppercase;margin:14pt 0 8pt 0;">'
            'IT IS HEREBY ORDERED THAT:</p>'
        )

        orders_with_costs = list(cleaned_orders)
        if costs_direction is None or not costs_direction.strip():
            costs_direction = "The costs of and incidental to this application shall be in the cause."
        orders_with_costs.append(costs_direction.strip())

        orders_html = (
            "<ol>"
            + "".join(f"<li>{o}</li>" for o in orders_with_costs)
            + "</ol>"
        )

        dated_block = (
            '<p class="dated">DATED at Lusaka this ______ day of '
            '________________________, 20____.</p>'
            '<div class="sig-line"></div>'
            '<p><strong>JUDGE</strong></p>'
        )

        drawn_by = (
            '<div class="served">'
            '<p><strong>Drawn by:</strong><br/>'
            f'{counsel_name or "[COUNSEL NAME]"}<br/>'
            f'{counsel_firm or "[FIRM NAME / CHAMBERS]"}<br/>'
            f'{firm_address or "[FIRM ADDRESS]"}<br/>'
            f'Counsel for the {applicant_role.capitalize()}'
            '</p>'
            '</div>'
        )

        template = _fetch_template(template_id)
        letterhead = pdf_tools.render_template_letterhead(template)

        body_md = "\n\n".join([
            letterhead,
            heading_html,
            doc_title,
            upon_recital,
            ordered_heading,
            orders_html,
            dated_block,
            drawn_by,
        ])

        artifact_title = (
            f"Draft Order — {applicant} v {respondent}"
            if respondent and len(applicant) < 30 and len(respondent) < 30
            else "Draft Order"
        )

        return await pdf_tools.pdf_generate_legal(
            title=artifact_title,
            body_markdown=body_md,
            meta_tool="draft_order",
            owner_id=owner_id,
            session_id=session_id,
        )

    async def _draft_application_bundle(
        summons_artifact_id: str,
        affidavit_artifact_id: str,
        skeletal_artifact_id: str,
        order_artifact_id: str,
        applicant_name: str,
        respondent_name: str,
        cause_of_action: str | None = None,
        procedural_mode: str | None = None,
        court_division: str | None = None,
        cause_number: str | None = None,
        include_cover: bool = True,
    ):
        """Merge the four application documents into one bundled PDF.

        Order: (optional cover) → Summons → Affidavit in Support → Skeletal
        Arguments → Draft Order. The cover page lists the matter, the
        documents inside, and the cause number.
        """
        from datetime import datetime

        applicant = (applicant_name or "").strip()
        respondent = (respondent_name or "").strip()
        if not applicant:
            return {"result": {"error": "applicant_name required"}}
        if not respondent:
            return {"result": {"error": "respondent_name required"}}

        parts: list[dict] = []

        if include_cover:
            today = datetime.utcnow().strftime("%-d %B %Y")
            cover_md = "\n\n".join([
                '<div class="court-caption">'
                '<div class="line">IN THE HIGH COURT FOR ZAMBIA</div>'
                + (f'<div class="line">{(court_division or "").upper()}</div>' if court_division else "")
                + '</div>',
                f'<div class="cause-number">Cause No. {cause_number or "[CAUSE NUMBER TO BE ALLOCATED]"}</div>',
                '<div class="between">B E T W E E N:</div>',
                '<table class="parties">'
                f'<tr><td>{applicant}</td><td class="right">APPLICANT</td></tr>'
                '<tr><td>AND</td><td></td></tr>'
                f'<tr><td>{respondent}</td><td class="right">RESPONDENT</td></tr>'
                '</table>',
                '<div class="doc-title">APPLICATION BUNDLE</div>',
                (
                    '<p style="text-align:center;font-style:italic;margin-top:14pt;">'
                    f'{cause_of_action or "Application"} '
                    f'{("by way of " + procedural_mode) if procedural_mode else ""}'
                    '</p>'
                ),
                '<p style="margin-top:24pt;"><strong>This bundle contains:</strong></p>',
                '<ol>'
                f'<li>{procedural_mode or "Originating Process"}</li>'
                '<li>Affidavit in Support</li>'
                '<li>Skeletal Arguments</li>'
                '<li>Draft Order</li>'
                '</ol>',
                f'<p class="dated">Filed: {today}</p>',
            ])

            cover = await pdf_tools.pdf_generate_legal(
                title=f"Application Bundle Cover — {applicant} v {respondent}",
                body_markdown=cover_md,
                meta_tool="application_bundle_cover",
                owner_id=owner_id,
                session_id=session_id,
            )
            cover_id = (cover.get("result") or {}).get("artifact_id")
            if cover_id:
                parts.append({"artifact_id": cover_id})

        for aid in [
            summons_artifact_id,
            affidavit_artifact_id,
            skeletal_artifact_id,
            order_artifact_id,
        ]:
            if not aid or not aid.strip():
                return {"result": {"error": "all four artifact_ids are required"}}
            parts.append({"artifact_id": aid.strip()})

        bundle_title = (
            f"Application Bundle — {applicant} v {respondent}"
            if len(applicant) < 30 and len(respondent) < 30
            else "Application Bundle"
        )

        return await pdf_tools.pdf_merge(
            parts=parts,
            title=bundle_title,
            owner_id=owner_id,
            session_id=session_id,
        )

    async def _draft_legal_document(
        title: str,
        body_markdown: str,
        template_id: str | None = None,
    ):
        """Render any non-litigation Zambian legal instrument (contract,
        deed, lease, power of attorney, will, statutory declaration, board
        resolution, demand letter, MOU, etc.) as a PDF in the formal legal
        layout (serif, justified, execution blocks).

        The agent composes the full body in Markdown following the Zambian
        drafting playbook in the system prompt — parties block, recitals,
        operative clauses, and the correct execution/attestation block for
        the instrument type. For court applications use the dedicated
        draft_summons / draft_affidavit / draft_skeletal / draft_order
        tools instead; this is for everything else."""
        if not title or not title.strip():
            return {"result": {"error": "title required"}}
        if not body_markdown or not body_markdown.strip():
            return {"result": {"error": "body_markdown required"}}

        template = _fetch_template(template_id)
        letterhead = pdf_tools.render_template_letterhead(template)
        body = "\n\n".join(filter(None, [letterhead, body_markdown]))

        return await pdf_tools.pdf_generate_legal(
            title=title.strip(),
            body_markdown=body,
            meta_tool="draft_legal_document",
            owner_id=owner_id,
            session_id=session_id,
        )

    async def _recommend_application(
        cause_of_action: str,
        procedural_mode: str,
        court_division: str,
        urgency: str,
        reliefs: list[str],
        documents_to_file: list[str],
        statutory_basis: list[str] | None = None,
        authorities: list[str] | None = None,
        notes: str | None = None,
    ):
        """Pure passthrough: the agent reasons about the plan, calls this tool
        with the structured result, and the frontend renders a plan card.

        The handler validates shape and emits an `application_plan` event via
        the tool envelope's `application_plan` field, which the agent loop
        forwards over SSE."""
        plan = {
            "cause_of_action": (cause_of_action or "").strip(),
            "procedural_mode": (procedural_mode or "").strip(),
            "court_division": (court_division or "").strip(),
            "urgency": (urgency or "inter_partes").strip(),
            "reliefs": [r.strip() for r in (reliefs or []) if r and r.strip()],
            "documents_to_file": [d.strip() for d in (documents_to_file or []) if d and d.strip()],
            "statutory_basis": [s.strip() for s in (statutory_basis or []) if s and s.strip()],
            "authorities": [a.strip() for a in (authorities or []) if a and a.strip()],
            "notes": (notes or "").strip() or None,
        }
        if not plan["cause_of_action"] or not plan["procedural_mode"]:
            return {
                "result": {
                    "error": "cause_of_action and procedural_mode are required",
                },
            }
        return {
            "result": {"plan": plan, "ok": True},
            "db_sources": [],
            "web_sources": [],
            # Surfaced separately by the agent loop as an `application_plan`
            # event so the UI can render a structured plan card inline.
            "application_plan": plan,
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
        "recommend_application": ToolDefinition(
            name="recommend_application",
            description=(
                "Propose the structured plan for a Zambian-court application "
                "BEFORE drafting any documents. Use this whenever the user "
                "describes a legal situation and wants help filing — e.g. "
                "'how do I sue X', 'I want an injunction', 'we need to "
                "challenge an unlawful arrest', 'apply for letters of "
                "administration', 'judicial review of a tribunal decision'.\n\n"
                "Fill the fields based on facts the user gave and corpus / "
                "web research you've done in this turn. The UI renders this "
                "as a Plan card the user can confirm before you call the "
                "drafting tools.\n\n"
                "PROCEDURAL MODE must be one of: 'Originating Notice of "
                "Motion', 'Originating Summons', 'Writ of Summons + "
                "Statement of Claim', 'Ex Parte Originating Notice of "
                "Motion', 'Petition', 'Inter Partes Summons', 'Ex Parte "
                "Summons', 'Notice of Motion'.\n\n"
                "COURT DIVISION must be one of: 'Principal Registry, Civil', "
                "'Principal Registry, Commercial', 'Principal Registry, "
                "Family and Children', 'Industrial Relations Division', "
                "'Constitutional Court', 'Court of Appeal', 'Subordinate "
                "Court'.\n\n"
                "URGENCY: 'ex_parte' (relief sought without notice to the "
                "respondent) or 'inter_partes' (with notice).\n\n"
                "RELIEFS: a numbered list of the orders prayed for, each in "
                "the imperative voice ('An order that the Respondent...'). "
                "DOCUMENTS_TO_FILE: list each filing the user will need "
                "(usually 'Originating Notice of Motion / Summons', "
                "'Affidavit in Support', 'Skeletal Arguments', 'Draft "
                "Order')."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "cause_of_action": {
                        "type": "string",
                        "description": "Named cause of action (e.g. 'Judicial review of an administrative decision', 'Application for habeas corpus', 'Specific performance of a sale-of-land contract', 'Unfair dismissal claim under the Employment Code Act, 2019').",
                    },
                    "procedural_mode": {
                        "type": "string",
                        "description": "One of the enumerated modes.",
                    },
                    "court_division": {
                        "type": "string",
                        "description": "Which Registry / Division of the High Court (or other court) the application should be filed in.",
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["ex_parte", "inter_partes"],
                    },
                    "reliefs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Numbered prayers for orders.",
                    },
                    "documents_to_file": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filings the user must prepare (Affidavit in Support, Skeletal Arguments, etc.).",
                    },
                    "statutory_basis": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Acts and sections grounding the application (e.g. 'Companies Act, 2017, Section 84', 'Order 53 of the Rules of the Supreme Court').",
                    },
                    "authorities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Cases the user should be ready to cite. Zambian citation form preferred (e.g. 'Attorney-General v Clarke (Appeal No. 96A/2004)').",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Short caveats or timing notes (e.g. limitation period, fee, urgency considerations).",
                    },
                },
                "required": [
                    "cause_of_action",
                    "procedural_mode",
                    "court_division",
                    "urgency",
                    "reliefs",
                    "documents_to_file",
                ],
            },
            handler=_recommend_application,
        ),
        "draft_legal_document": ToolDefinition(
            name="draft_legal_document",
            description=(
                "Draft any NON-litigation Zambian legal instrument as a PDF "
                "in formal legal layout. Use for: contract of sale of land, "
                "deed of assignment, lease / tenancy agreement, employment "
                "contract, contract for services, power of attorney, will, "
                "statutory declaration, board resolution, shareholders' "
                "agreement, memorandum of understanding, demand / letter "
                "before action, deed of guarantee, loan / facility "
                "agreement, settlement / consent, and similar.\n\n"
                "DO NOT use this for court applications — those have "
                "dedicated tools (draft_summons / draft_affidavit / "
                "draft_skeletal / draft_order / draft_application_bundle).\n\n"
                "You compose the full body as Markdown following the Zambian "
                "drafting playbook: a parties block, recitals (WHEREAS …) "
                "where appropriate, numbered operative clauses, and the "
                "CORRECT execution / attestation block for the instrument — "
                "e.g. a deed is 'signed, sealed and delivered' and witnessed; "
                "a statutory declaration ends with the statutory-declaration "
                "jurat before a Commissioner for Oaths; a will needs the "
                "attestation clause + two witnesses; a board resolution "
                "records the meeting, quorum and resolution number. For land "
                "instruments include the consent-to-assign / Property "
                "Transfer Tax (8%) / Lands and Deeds Registry steps where "
                "relevant. Use bracketed [PLACEHOLDERS] for details the user "
                "hasn't supplied rather than inventing them."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Document title shown on the artifact card, e.g. 'Contract of Sale of Land — Banda to Phiri' or 'General Power of Attorney'.",
                    },
                    "body_markdown": {
                        "type": "string",
                        "description": "The COMPLETE instrument as Markdown: heading, parties, recitals, numbered clauses, and the correct execution/attestation block. Headings (##), numbered lists, and bold render in the legal layout.",
                    },
                    "template_id": {
                        "type": "string",
                        "description": "Optional ID of one of the user's saved templates (from suggest_templates); prepends the firm letterhead.",
                    },
                },
                "required": ["title", "body_markdown"],
            },
            handler=_draft_legal_document,
        ),
        "draft_summons": ToolDefinition(
            name="draft_summons",
            description=(
                "Draft the originating process for a Zambian-court application "
                "and save it as a PDF artifact. Use AFTER the user has "
                "confirmed the plan from `recommend_application`. Renders the "
                "standard Zambian court caption (IN THE HIGH COURT FOR ZAMBIA "
                "/ AT THE [REGISTRY] / HOLDEN AT [CITY] / jurisdiction line), "
                "the cause number, the BETWEEN parties block, the document "
                "title (e.g. 'ORIGINATING NOTICE OF MOTION'), the recital "
                "('TAKE NOTICE that...' or 'LET [respondent]...' depending on "
                "mode), the numbered reliefs, the cross-reference to the "
                "Affidavit in Support and Skeletal Arguments, the dated line, "
                "signature block, and address for service.\n\n"
                "Fill `procedural_mode` and `court_division` from the "
                "confirmed plan. If the user did not give you the parties' "
                "names, ask first — do not invent them. If the user did not "
                "give a cause number, leave `cause_number` empty and the tool "
                "renders `[YEAR]/[REGISTRY_CODE]/[NUMBER]` for the law firm "
                "to fill at filing."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "procedural_mode": {
                        "type": "string",
                        "description": "The originating process type, copied from the confirmed plan (e.g. 'Originating Notice of Motion', 'Ex Parte Originating Notice of Motion', 'Originating Summons', 'Writ of Summons + Statement of Claim', 'Petition').",
                    },
                    "court_division": {
                        "type": "string",
                        "description": "Court division copied from the confirmed plan.",
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["ex_parte", "inter_partes"],
                        "description": "Copied from the confirmed plan.",
                    },
                    "applicant_name": {
                        "type": "string",
                        "description": "The party bringing the application (Plaintiff / Applicant / Petitioner). Use the user's real name where given; otherwise ask before drafting.",
                    },
                    "respondent_name": {
                        "type": "string",
                        "description": "The party the relief is sought against.",
                    },
                    "reliefs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Numbered prayers for orders. Each entry should be a complete sentence in the imperative ('An order that...').",
                    },
                    "cause_of_action": {
                        "type": "string",
                        "description": "Short label for the cause of action (e.g. 'Unfair dismissal under the Employment Code Act, 2019').",
                    },
                    "cause_number": {
                        "type": "string",
                        "description": "Cause number in the form YEAR/REGISTRY_CODE/NUMBER. Leave empty if not yet allocated — the tool will render a placeholder.",
                    },
                    "statutory_basis": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Acts / sections / Rules the application is brought under. Rendered as a 'Pursuant to ...' italic line under the document title.",
                    },
                    "supporting_deponent": {
                        "type": "string",
                        "description": "Name of the person who will swear the supporting Affidavit. Defaults to the applicant if omitted.",
                    },
                    "counsel_name": {
                        "type": "string",
                        "description": "Counsel's name for the signature block. Leave empty for a placeholder.",
                    },
                    "counsel_firm": {
                        "type": "string",
                        "description": "Counsel's firm / chambers for the signature block.",
                    },
                    "applicant_address": {
                        "type": "string",
                        "description": "Applicant's address — used in the 'Dated at [city] ...' line; falls back to 'Lusaka'.",
                    },
                    "respondent_address": {
                        "type": "string",
                        "description": "Respondent's address for service. Required for inter partes applications; ignored for ex parte.",
                    },
                    "return_date_note": {
                        "type": "string",
                        "description": "Optional override for the return-date phrase (default: 'on a date to be appointed by the Honourable Court').",
                    },
                    "template_id": {
                        "type": "string",
                        "description": "ID of one of the user's saved templates (returned by `suggest_templates`). When provided, the tool prepends the template's letterhead (centred, with the firm name + address + boilerplate from the template's preview text) above the court caption so the draft carries the chambers' branding. Leave empty to render in the default house format.",
                    },
                },
                "required": [
                    "procedural_mode",
                    "court_division",
                    "applicant_name",
                    "respondent_name",
                    "reliefs",
                ],
            },
            handler=_draft_summons,
        ),
        "draft_affidavit": ToolDefinition(
            name="draft_affidavit",
            description=(
                "Draft an Affidavit in Support and save it as a PDF artifact. "
                "Call AFTER `draft_summons` (or alongside it as part of the "
                "bundle). Renders the same court caption + parties block as "
                "the summons, then the standard Zambian deposition opening "
                "('I, [DEPONENT], of [ADDRESS], …, do solemnly and sincerely "
                "make oath and state as follows:'), then numbered THAT-"
                "statements, then the jurat (SWORN at … BEFORE ME …), then "
                "an exhibits index.\n\n"
                "The first and last numbered paragraphs are added "
                "automatically: the first one says the deponent is the "
                "Applicant/Respondent and the facts are within their personal "
                "knowledge; the last one prays the Court grant the orders in "
                "the originating process. Pass the substantive facts in "
                "between via `facts` — each item becomes one numbered "
                "paragraph. Prefix with 'THAT' is optional (added if "
                "missing).\n\n"
                "Exhibits: each exhibit is {label, description}; the label is "
                "the deponent's-initials + index (e.g. 'MB1', 'MB2'). The "
                "tool only renders the exhibits index — the actual exhibit "
                "PDFs are merged later by `draft_application_bundle`."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "procedural_mode": {
                        "type": "string",
                        "description": "Originating-process type — same value as passed to draft_summons.",
                    },
                    "court_division": {
                        "type": "string",
                    },
                    "applicant_name": {"type": "string"},
                    "respondent_name": {"type": "string"},
                    "cause_number": {
                        "type": "string",
                        "description": "Must match the one used by draft_summons. Leave empty for a placeholder.",
                    },
                    "deponent_name": {
                        "type": "string",
                        "description": "The person swearing the affidavit. Usually the applicant; sometimes a witness or counsel's clerk.",
                    },
                    "deponent_address": {
                        "type": "string",
                        "description": "Full address of the deponent — e.g. 'Plot 1234, Kabulonga, Lusaka'.",
                    },
                    "deponent_occupation": {
                        "type": "string",
                        "description": "Occupation phrase — e.g. 'an accountant', 'a marketing executive', 'unemployed'.",
                    },
                    "deponent_role": {
                        "type": "string",
                        "description": "Role of the deponent in the matter (Applicant, Respondent, Petitioner, Witness). Defaults to Applicant.",
                    },
                    "deponent_gender": {
                        "type": "string",
                        "description": "Bare gender word ('male' or 'female') OR a pre-composed phrase like 'adult Zambian male of full legal capacity'.",
                    },
                    "facts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Substantive THAT-paragraphs. One per fact. Prefix 'THAT' optional. The intro and prayer paragraphs are added automatically.",
                    },
                    "supporting_document": {
                        "type": "string",
                        "description": "Document this Affidavit supports — defaults to the procedural_mode (e.g. 'Originating Notice of Motion').",
                    },
                    "exhibits": {
                        "type": "array",
                        "description": "Exhibits index entries. Each item: {label, description}. Label defaults to deponent-initials + index.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "description": {"type": "string"},
                            },
                        },
                    },
                    "commissioner_name": {
                        "type": "string",
                        "description": "Optional — fills the COMMISSIONER FOR OATHS slot. Leave empty for a placeholder.",
                    },
                    "sworn_at_city": {
                        "type": "string",
                        "description": "City where the affidavit will be sworn. Defaults to Lusaka.",
                    },
                    "template_id": {
                        "type": "string",
                        "description": "ID of one of the user's saved templates (returned by `suggest_templates`). When provided, the tool prepends the template's letterhead above the court caption. Leave empty to render in the default house format.",
                    },
                },
                "required": [
                    "procedural_mode",
                    "court_division",
                    "applicant_name",
                    "respondent_name",
                    "deponent_name",
                    "deponent_address",
                    "deponent_occupation",
                    "facts",
                ],
            },
            handler=_draft_affidavit,
        ),
        "draft_skeletal": ToolDefinition(
            name="draft_skeletal",
            description=(
                "Draft Skeletal Arguments in support of an application and "
                "save as a PDF artifact. Call AFTER `draft_summons` and "
                "`draft_affidavit` (the affidavit lays out the facts; "
                "skeletal arguments lay out the law). Uses the IRAC-style "
                "structure Zambian counsel use:\n\n"
                "  1.0 INTRODUCTION       — short paragraphs framing the matter\n"
                "  2.0 ISSUES FOR DETERMINATION — numbered 'Whether…' questions\n"
                "  3.0 SUBMISSIONS        — one block per submission, "
                "                            each with paragraphs + cited authorities\n"
                "  4.0 PRAYER             — what the Court is asked to do\n"
                "  LIST OF AUTHORITIES    — cases + statutes, separated\n\n"
                "Pull statutory citations from a prior `search_corpus` so "
                "they reference the actual section text. Case citations "
                "should use Zambian form where available (Appeal No., SCZ "
                "Appeal No., Supreme Court Judgment No., etc.)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "procedural_mode": {"type": "string"},
                    "court_division": {"type": "string"},
                    "applicant_name": {"type": "string"},
                    "respondent_name": {"type": "string"},
                    "cause_number": {"type": "string"},
                    "supporting_document": {
                        "type": "string",
                        "description": "Document this Skeletal supports — defaults to procedural_mode.",
                    },
                    "introduction": {
                        "type": "string",
                        "description": "Introductory paragraphs as plain prose. Use double-newlines between paragraphs; the tool numbers them 1.1, 1.2, etc.",
                    },
                    "issues": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Numbered 'Whether X' questions for the Court to decide.",
                    },
                    "submissions": {
                        "type": "array",
                        "description": "One block per submission. Each: {title, paragraphs[], citations[]}. Title becomes the heading (e.g. 'The dismissal was substantively unfair'). Paragraphs become 3.X.Y numbered points. Citations are listed under the paragraphs in italics.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "paragraphs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "citations": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Statute citations or case names backing the submission.",
                                },
                            },
                            "required": ["paragraphs"],
                        },
                    },
                    "prayer": {
                        "type": "string",
                        "description": "Final prayer paragraph — usually 'WHEREFORE the Applicant prays…' or 'For the reasons above the Applicant respectfully prays that this Honourable Court grants the orders sought…'",
                    },
                    "authorities_cases": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Cases relied upon, formatted in Zambian citation style.",
                    },
                    "authorities_statutes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Statutes / Rules relied upon (Acts, sections, Order numbers).",
                    },
                    "counsel_name": {"type": "string"},
                    "counsel_firm": {"type": "string"},
                    "template_id": {
                        "type": "string",
                        "description": "ID of one of the user's saved templates (returned by `suggest_templates`). When provided, the tool prepends the template's letterhead above the court caption. Leave empty to render in the default house format.",
                    },
                },
                "required": [
                    "procedural_mode",
                    "court_division",
                    "applicant_name",
                    "respondent_name",
                    "introduction",
                    "issues",
                    "submissions",
                    "prayer",
                ],
            },
            handler=_draft_skeletal,
        ),
        "draft_order": ToolDefinition(
            name="draft_order",
            description=(
                "Draft a Draft Order for the Judge to endorse, and save as a "
                "PDF artifact. This is the fourth and final document in the "
                "application bundle. Call AFTER `draft_skeletal`. Renders the "
                "standard form: same court caption + parties block, "
                "'DRAFT ORDER' title, the UPON-recital (which references the "
                "Originating Process + Affidavit + Skeletal Arguments + the "
                "hearing), 'IT IS HEREBY ORDERED THAT:', the numbered orders "
                "(reliefs the Applicant prays for, phrased in the imperative "
                "the Judge would actually write), a costs direction, dated "
                "line, JUDGE signature line, and a Drawn-by chambers block."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "procedural_mode": {"type": "string"},
                    "court_division": {"type": "string"},
                    "applicant_name": {"type": "string"},
                    "respondent_name": {"type": "string"},
                    "cause_number": {"type": "string"},
                    "urgency": {
                        "type": "string",
                        "enum": ["ex_parte", "inter_partes"],
                    },
                    "orders": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Numbered orders the Judge would make. Phrased in the imperative ('That the Respondent's dismissal of the Applicant is declared null and void.'). Mirror the reliefs from the originating process but in the voice of the Court.",
                    },
                    "supporting_deponent": {
                        "type": "string",
                        "description": "Name of the deponent referenced in the UPON-reading clause. Defaults to the applicant.",
                    },
                    "costs_direction": {
                        "type": "string",
                        "description": "Costs paragraph appended after the substantive orders. Default: 'The costs of and incidental to this application shall be in the cause.' Common alternatives: 'paid by the Respondent', 'reserved'.",
                    },
                    "counsel_name": {"type": "string"},
                    "counsel_firm": {"type": "string"},
                    "firm_address": {"type": "string"},
                    "template_id": {
                        "type": "string",
                        "description": "ID of one of the user's saved templates (returned by `suggest_templates`). When provided, the tool prepends the template's letterhead above the court caption. Leave empty to render in the default house format.",
                    },
                },
                "required": [
                    "procedural_mode",
                    "court_division",
                    "applicant_name",
                    "respondent_name",
                    "orders",
                ],
            },
            handler=_draft_order,
        ),
        "draft_application_bundle": ToolDefinition(
            name="draft_application_bundle",
            description=(
                "Merge the four application documents — Summons, Affidavit "
                "in Support, Skeletal Arguments, Draft Order — into a single "
                "bundled PDF artifact in the order they're handed up at "
                "filing. Optionally prepends a cover page with the matter, "
                "the parties, cause number, and an index. Call this AFTER "
                "all four drafting tools have run successfully. Pass the "
                "artifact_id returned by each of the four draft tools."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "summons_artifact_id": {
                        "type": "string",
                        "description": "artifact_id returned by `draft_summons`.",
                    },
                    "affidavit_artifact_id": {
                        "type": "string",
                        "description": "artifact_id returned by `draft_affidavit`.",
                    },
                    "skeletal_artifact_id": {
                        "type": "string",
                        "description": "artifact_id returned by `draft_skeletal`.",
                    },
                    "order_artifact_id": {
                        "type": "string",
                        "description": "artifact_id returned by `draft_order`.",
                    },
                    "applicant_name": {"type": "string"},
                    "respondent_name": {"type": "string"},
                    "cause_of_action": {"type": "string"},
                    "procedural_mode": {"type": "string"},
                    "court_division": {"type": "string"},
                    "cause_number": {"type": "string"},
                    "include_cover": {
                        "type": "boolean",
                        "description": "Defaults true. Set false to skip the cover page if the user just wants the four documents concatenated.",
                    },
                },
                "required": [
                    "summons_artifact_id",
                    "affidavit_artifact_id",
                    "skeletal_artifact_id",
                    "order_artifact_id",
                    "applicant_name",
                    "respondent_name",
                ],
            },
            handler=_draft_application_bundle,
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
