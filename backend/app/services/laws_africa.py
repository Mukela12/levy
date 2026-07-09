"""
Laws.Africa Content API client.

Laws.Africa (the platform behind ZambiaLII / AfricanLII) exposes Zambian
legislation AND judgments through a sanctioned, token-authenticated API —
the legitimate alternative to scraping ZambiaLII (whose robots.txt blocks
AI crawlers). Content is addressed by FRBR URI, e.g.:

    /akn/zm/act/2019/3            Employment Code Act, 2019
    /akn/zm/judgment/...          a judgment

Auth: a free Laws.Africa account yields a token; pass it as
    Authorization: Token <token>
Base: https://api.laws.africa/v3/

LICENSING NOTE: the underlying content is generally CC-BY-NC-SA
(non-commercial). If Levy is operated commercially, a commercial licence
from Laws.Africa is required before ingesting their content into the
product corpus. This client is gated on `LAWS_AFRICA_API_TOKEN` and stays
inert until a token is configured.

Docs: https://developers.laws.africa/api/about-the-api
"""

from __future__ import annotations

from typing import Any, Iterator

import httpx

from ..config import get_settings

BASE = "https://api.laws.africa/v3"


def _token() -> str | None:
    tok = (get_settings().laws_africa_api_token or "").strip()
    return tok or None


def is_configured() -> bool:
    return _token() is not None


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Token {_token()}",
        "User-Agent": "Levy/1.0 (+https://levy-ten.vercel.app)",
    }


def _client() -> httpx.Client:
    return httpx.Client(timeout=60.0, follow_redirects=True, headers=_headers())


def get_work(frbr_uri: str, fmt: str = "json") -> Any:
    """Fetch a single work (Act / judgment) by FRBR URI.

    fmt: 'json' (metadata + structured body), 'html', 'xml' (Akoma Ntoso),
    'pdf' (returns bytes). frbr_uri like '/akn/zm/act/2019/3'.
    """
    uri = frbr_uri if frbr_uri.startswith("/") else f"/{frbr_uri}"
    url = f"{BASE}{uri}.{fmt}"
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
        return r.content if fmt == "pdf" else r.json()


def list_works(country: str = "zm", *, page_size: int = 100) -> Iterator[dict]:
    """Yield work-metadata dicts for a country (default Zambia).

    Paginates the /v3/akn/<country>/ listing. Each item carries at least
    `frbr_uri`, `title`, `nature` (act / judgment), `year`, and citation
    fields. Stops when the API stops returning a `next` page.
    """
    url: str | None = f"{BASE}/akn/{country}/"
    with _client() as c:
        while url:
            r = c.get(url, params={"page_size": page_size} if "page" not in (url or "") else None)
            r.raise_for_status()
            data = r.json()
            # The listing endpoint returns either a paginated {results,next}
            # envelope or a bare list depending on the route; handle both.
            if isinstance(data, dict):
                for item in data.get("results", []):
                    yield item
                url = data.get("next")
            elif isinstance(data, list):
                for item in data:
                    yield item
                url = None
            else:
                url = None


def search(query: str, *, country: str = "zm", nature: str | None = None, page_size: int = 20) -> list[dict]:
    """Full-text search across Laws.Africa content, scoped to a country and
    optionally a nature ('judgment' or 'act'). Returns the result list."""
    params: dict[str, Any] = {"q": query, "country": country, "page_size": page_size}
    if nature:
        params["nature"] = nature
    with _client() as c:
        r = c.get(f"{BASE}/search/{country}/", params=params)
        r.raise_for_status()
        data = r.json()
        return data.get("results", []) if isinstance(data, dict) else (data or [])


def ping() -> dict:
    """Lightweight connectivity + auth check. Returns a small diagnostic."""
    if not is_configured():
        return {"ok": False, "reason": "LAWS_AFRICA_API_TOKEN not set"}
    try:
        with _client() as c:
            r = c.get(f"{BASE}/akn/zm/", params={"page_size": 1})
        return {"ok": r.status_code == 200, "status": r.status_code, "sample": r.text[:300]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": str(e)}
