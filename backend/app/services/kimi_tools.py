"""Moonshot's search and fetch REST tools, used only where ours come back empty.

Measured against Levy's own stack on 21 September 2026, on real Zambian
lookups:

  Fetch ($0.002 a call, billed only when it returns text)
    * It OCRs scanned PDFs. On six Parliament scans that pdfplumber reads as
      1-3 characters it returned 1,600-5,700 characters of real text.
    * Apple Vision still reads those scans better (non-word rate 0.18/0.29/
      0.22 against Kimi's 0.23/0.59/0.25) and its transcriptions stay page
      aligned, so bulk OCR on the Mac stays with Vision.
    * It truncates long PDFs at roughly 47k characters, where our own
      extraction of the same Act returned 97-109k, and its markdown carries
      no page numbers, so it can never be the primary reader for a document
      Levy cites by page.
    * parliament.gov.zm HTML pages fail every time (502); ours read them.

  Search Pro ($0.003 a call)
    * Restricted to official sites it returned 5/5 official sources with the
      statutory text as passages; on the open web only 0-2 of 5 were
      official. But it accepts at most FIVE domains, and Levy's allowlist
      runs to dozens, so Tavily stays the primary search.

So this module is a fallback: it runs when our own tools return nothing, and
costs nothing when they succeed.
"""
from __future__ import annotations

import logging

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)
BASE = "https://api.moonshot.ai/v1/tools"
TIMEOUT = 45.0
# Kimi caps `sites` at five, so this is Levy's five most-cited official
# publishers rather than the full gov allowlist Tavily receives.
CORE_SITES = ["parliament.gov.zm", "judiciaryzambia.com", "mlss.gov.zm", "rtsa.org.zm", "zra.org.zm"]


def is_configured() -> bool:
    settings = get_settings()
    return bool(getattr(settings, "kimi_tools_enabled", True)) and bool(settings.moonshot_api_key)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().moonshot_api_key}",
            "Content-Type": "application/json"}


async def fetch_url(url: str) -> dict | None:
    """Page or PDF text as markdown, or None when it cannot be read.

    Billed only when markdown comes back non-blank, so a failure is free.
    """
    if not is_configured() or not (url or "").lower().startswith(("http://", "https://")):
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(f"{BASE}/fetch", headers=_headers(), json={"url": url})
        if r.status_code != 200:
            logger.info("kimi fetch %s for %s", r.status_code, url[:120])
            return None
        body = r.json()
    except Exception:  # noqa: BLE001 — a fallback must never break the tool that called it
        logger.warning("kimi fetch failed", exc_info=True)
        return None
    markdown = (body.get("markdown") or "").strip()
    if not markdown:
        return None
    return {"title": body.get("title") or "", "markdown": markdown, "url": body.get("url") or url}


async def search_official(query: str, limit: int = 3, sites: list[str] | None = None) -> list[dict]:
    """Official-site search that returns passages, not just links."""
    if not is_configured() or not (query or "").strip():
        return []
    payload = {"text_query": query, "limit": max(1, min(limit, 10)),
               "sites": (sites or CORE_SITES)[:5]}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(f"{BASE}/search_pro", headers=_headers(), json=payload)
        if r.status_code != 200:
            logger.info("kimi search_pro %s", r.status_code)
            return []
        results = r.json().get("search_results") or []
    except Exception:  # noqa: BLE001
        logger.warning("kimi search_pro failed", exc_info=True)
        return []
    out = []
    for item in results:
        # One call returned 13k-50k characters of passages. Trimmed here, not
        # in the model's context, where it would cost ten times the API fee.
        passages = [(c.get("text") or "").strip() for c in (item.get("chunks") or [])]
        joined = "\n".join(p for p in passages if p)[:2000]
        out.append({
            "title": item.get("title") or "",
            "url": item.get("url") or "",
            "site": item.get("site_name") or "",
            "date": item.get("date") or "",
            "content": joined or (item.get("snippet") or "")[:2000],
        })
    return out
