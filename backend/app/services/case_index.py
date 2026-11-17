"""ZambiaLII's judgment index, through Laws.Africa's licensed API.

Levy must never scrape zambialii.org and never ingests the Zambia Law
Reports. This is the permitted route to the same collection: Laws.Africa,
which runs ZambiaLII's platform, sells API access to a "Knowledge Base" of
Zambian judgments. A query returns, for each case, its title with cause
number and neutral citation, the court, the date, a summary of the facts,
issues and holding, and the public link. It does NOT return the judgment
text, so it can prove a case exists and correct its citation, and it can
say what the summary records, but it can never support a quotation.

Measured on 17 Nov 2026 (free Sandbox plan, 30 calls a minute, 100 a day):
  * about half the calls failed (503, 500, timeouts) and a cold call took
    21 seconds against 2 for a warm one, so every call here is best-effort
    with a timeout, and a short circuit breaker stops a dead service from
    adding a 20-second wait to every answer;
  * scores are not comparable between queries: an invented case scored 1,974
    on its respondent's name alone. A hit is therefore decided by the party
    names in the returned title, never by the score;
  * only successful calls count against the quota, and the response headers
    say how many are left, so the daily budget needs no counter of our own.

The quota is spent in two places only: checking a cited case that neither
the library nor the citator knows (purpose "verify"), and finding authority
when the library has no case on the point (purpose "search"). A share of the
day is held back for verification, and every result is cached so the same
case is never paid for twice.
"""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx

from ..config import get_settings

BASE = "https://api.laws.africa/ai/v1/knowledge-bases"
CACHE_DAYS = 30
TIMEOUT_SECONDS = 22.0          # under the agent's 25-second tool timeout
BREAKER_FAILS = 2               # consecutive failures before the breaker opens
BREAKER_SECONDS = 300

_lock = threading.Lock()
_state: dict = {"day_remaining": None, "day_reset_at": 0.0, "minute_remaining": None,
                "minute_reset_at": 0.0, "fails": 0, "down_until": 0.0}
_mem: dict[str, tuple[float, list[dict]]] = {}
_table = {"missing_until": 0.0}   # the lookups table is optional; do not ask for it on every call


def configured() -> bool:
    s = get_settings()
    return bool(getattr(s, "case_index_enabled", True) and getattr(s, "laws_africa_api_key", ""))


def _key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())).strip()[:300]


_RL = re.compile(r'"(minute|hour|day)"\s*;\s*r=(\d+)\s*;\s*t=(\d+)')


def _read_ratelimit(header: str | None) -> None:
    """ `"minute";r=24;t=18, "day";r=82;t=31018` -> what is left, and until when."""
    now = time.time()
    for window, remaining, seconds in _RL.findall(header or ""):
        if window in ("minute", "day"):
            _state[f"{window}_remaining"] = int(remaining)
            _state[f"{window}_reset_at"] = now + int(seconds)


def remaining_today() -> int | None:
    """Calls left in the UTC day, when the service has told us; else None."""
    if _state["day_remaining"] is None or time.time() >= _state["day_reset_at"]:
        return None
    return _state["day_remaining"]


def allowed(purpose: str) -> bool:
    """May this call be spent? Verification outranks searching."""
    now = time.time()
    if now < _state["down_until"]:
        return False
    if _state["minute_remaining"] == 0 and now < _state["minute_reset_at"]:
        return False
    left = remaining_today()
    if left is None:
        return True
    reserve = int(getattr(get_settings(), "case_index_verify_reserve", 30)) if purpose == "search" else 0
    return left > reserve


def _clean(item: dict) -> dict:
    meta = item.get("metadata") or {}
    court = meta.get("court") or {}
    return {
        "title": meta.get("title") or "",
        "citation": meta.get("neutral_citation") or "",
        "court": court.get("name") if isinstance(court, dict) else "",
        "date": meta.get("expression_date") or "",
        "url": meta.get("public_url") or "",
        "summary": ((item.get("content") or {}).get("text") or "").strip(),
        "flynote": (meta.get("flynote") or "").strip(),
        "score": item.get("score"),
    }


def _cache_get(key: str) -> list[dict] | None:
    hit = _mem.get(key)
    if hit and time.time() - hit[0] < CACHE_DAYS * 86400:
        return hit[1]
    if time.time() < _table["missing_until"]:
        return None
    try:
        from ..db.supabase import get_db
        since = (datetime.now(timezone.utc) - timedelta(days=CACHE_DAYS)).isoformat()
        rows = (get_db().table("case_index_lookups").select("results,created_at")
                .eq("query", key).eq("status", "ok").gte("created_at", since)
                .order("created_at", desc=True).limit(1).execute().data or [])
        if rows and isinstance(rows[0].get("results"), list):
            _mem[key] = (time.time(), rows[0]["results"])
            return rows[0]["results"]
    except Exception:  # noqa: BLE001 — the table is optional; memory still caches
        _table["missing_until"] = time.time() + 600
    return None


def _record(purpose: str, key: str, status: str, ms: int, results: list[dict] | None) -> None:
    """One row per call that reached the service: the cache and the usage log."""
    if time.time() < _table["missing_until"]:
        return
    try:
        from ..db.supabase import get_db
        get_db().table("case_index_lookups").insert({
            "purpose": purpose, "query": key, "status": status, "latency_ms": ms,
            "hits": len(results or []), "results": results if status == "ok" else None,
            "day_remaining": remaining_today(),
        }).execute()
    except Exception:  # noqa: BLE001
        pass


def retrieve(text: str, top_k: int = 5, purpose: str = "search") -> dict:
    """Query the judgments index. Never raises.

    {"ok": True, "results": [...], "cached": bool} or
    {"ok": False, "error": "unconfigured" | "budget" | "unavailable", "results": []}
    """
    key = _key(text)
    if not key:
        return {"ok": False, "error": "empty", "results": []}
    if not configured():
        return {"ok": False, "error": "unconfigured", "results": []}
    cached = _cache_get(key)
    if cached is not None:
        return {"ok": True, "results": cached[:top_k], "cached": True}
    with _lock:
        if not allowed(purpose):
            return {"ok": False, "error": "budget" if time.time() >= _state["down_until"] else "unavailable",
                    "results": []}
    settings = get_settings()
    code = getattr(settings, "case_index_kb", "") or "judgments-zm"
    started = time.time()
    status, results = "error", None
    try:
        resp = httpx.post(f"{BASE}/{code}/retrieve",
                          headers={"Authorization": f"Bearer {settings.laws_africa_api_key}"},
                          json={"text": text[:500], "top_k": max(1, min(int(top_k or 5), 10))},
                          timeout=TIMEOUT_SECONDS)
        _read_ratelimit(resp.headers.get("RateLimit"))
        if resp.status_code == 200:
            results = [_clean(r) for r in (resp.json().get("results") or [])]
            status = "ok"
        elif resp.status_code == 429:
            status = "throttled"
            wait = int(resp.headers.get("Retry-After") or 60)
            _state["down_until"] = time.time() + min(max(wait, 5), 3600)
        else:
            status = f"http_{resp.status_code}"
    except httpx.TimeoutException:
        status = "timeout"
    except Exception:  # noqa: BLE001
        status = "error"
    ms = int((time.time() - started) * 1000)
    with _lock:
        if status == "ok":
            _state["fails"] = 0
            _mem[key] = (time.time(), results or [])
        elif status != "throttled":
            _state["fails"] += 1
            if _state["fails"] >= BREAKER_FAILS:
                _state["down_until"] = time.time() + BREAKER_SECONDS
                _state["fails"] = 0
    _record(purpose, key, status, ms, results)
    if status != "ok":
        print(f"[case_index] {purpose} lookup failed: {status} after {ms} ms")
        return {"ok": False, "error": "unavailable", "results": []}
    return {"ok": True, "results": (results or [])[:top_k], "cached": False}


def _years(text: str) -> set[str]:
    return set(re.findall(r"\b((?:19|20)\d{2})\b", text or ""))


def lookup_case(a: str, b: str, cite: str = "") -> dict | None:
    """Is the case "A v B" in the index? Decided by the names, not the score.

    Returns None when the index could not be asked (down, over budget, not
    configured): unknown, not absent. Otherwise {"found": False} or
    {"found": True, "title", "citation", "court", "date", "url", "conflict"}.
    `conflict` is set when the answer's citation carries a cause number or a
    year that the indexed case does not: the name is right, the citation is not.
    """
    from .citation_audit import _case_in, _norm, _numbers_conflict, _party_tokens, _too_generic
    ta, tb = _party_tokens(a), _party_tokens(b)
    if _too_generic(ta, tb) or len(ta) + len(tb) < 3:
        return None
    res = retrieve(f"{a} v {b}", top_k=5, purpose="verify")
    if not res.get("ok"):
        return None
    for r in res["results"]:
        title = _norm(r.get("title") or "")
        # An appeal reverses the order of the parties, so either order is the case.
        if _case_in(ta, tb, title) or _case_in(tb, ta, title):
            cited_years, listed_years = _years(cite), _years(r.get("title") or "")
            conflict = _numbers_conflict(cite, r.get("title") or "") or bool(
                cited_years and listed_years and not (cited_years & listed_years))
            return {"found": True, "title": r["title"], "citation": r.get("citation") or "",
                    "court": r.get("court") or "", "date": r.get("date") or "", "url": r.get("url") or "",
                    "conflict": conflict}
    return {"found": False}
