"""Levy's shared memory of recent, verified legal facts.

The library is a snapshot and the law moves: commencement orders, a Budget's
PAYE bands, a new wage order, a repeal. When an answer finds such a fact on an
official site, it records it here and every later answer sees it, whoever asks.

Nothing about the person asking is kept. A row is a public fact, the official
URL it came from, and a passage the SERVER found on that page itself: the
model proposes, the server fetches the page and checks the words. A quote that
is not on the page is refused; a page that cannot be fetched leaves the row
pending, unseen until the watcher (services/watcher.py) confirms it.

    pending    recorded, not yet confirmed on the page: never shown
    verified   confirmed on an official page: shown to every answer, labelled
               as an update newer than the library
    approved   confirmed by a person as well: may also change a calculator
               (an approved "paye-bands-2027" row sets the 2027 PAYE bands)
    rejected, superseded   kept for the record, never shown

Table: legal_updates (supabase/migrations/20261012000000_*). Every function
here fails soft: if the table is missing or the database is down, answers go
on exactly as before.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from datetime import date, datetime, timezone
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

KINDS = ("commencement", "new_law", "amendment", "repeal", "rate_change", "court_rule", "other")
SHOWN = ("verified", "approved")
# Official sources only: government domains and the statutory regulators whose
# publications carry legal effect. Not news, not ZambiaLII, not law firms.
OFFICIAL_SUFFIXES = (".gov.zm",)
OFFICIAL_HOSTS = (
    "parliament.gov.zm", "zra.org.zm", "boz.zm", "napsa.co.zm", "nhima.co.zm", "judiciaryzambia.com",
    "pacra.org.zm", "zppa.org.zm", "lawsofzambia.com", "pia.org.zm", "seczambia.org.zm", "ccpc.org.zm",
    "zicta.zm", "erb.org.zm", "zema.org.zm", "zda.org.zm", "rtsa.org.zm", "zambiaimmigration.gov.zm",
)
QUOTE_MATCH = 0.9          # share of the quote's 8-letter runs that must be on the page
MAX_PER_DAY = 60           # a ceiling on new rows a day, whatever the cause
CACHE_SECONDS = 600
PROMPT_LIMIT = 25

_PII = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.]+"                      # e-mail
    r"|(?:\+?260|\b0)[79]\d{8}\b"                    # Zambian mobile number
    r"|\b\d{6}/\d{2}/\d\b"                           # NRC number
    r"|\b\d{10,}\b",                                 # account-like digit runs
)
# First person about one's own affairs ("my employer", "I was dismissed"), not
# "Category I" or "Part I".
_PRIVATE = re.compile(r"\b(?:my|our) (?:client|employer|employee|case|matter|company|landlord|tenant)\b"
                      r"|\bI(?:'m| am| was| have| had)\b", re.I)

_cache: dict[str, tuple[float, object]] = {}


def official(url: str) -> bool:
    host = (urlparse(url or "").hostname or "").lower()
    if not host or "zambialii" in host:
        return False
    host = host[4:] if host.startswith("www.") else host
    return host.endswith(OFFICIAL_SUFFIXES) or any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS)


def topic_key(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (topic or "").lower()).strip("-")[:80]


def statement_hash(statement: str) -> str:
    norm = re.sub(r"[^a-z0-9]+", " ", (statement or "").lower()).strip()
    return hashlib.sha256(norm.encode()).hexdigest()[:32]


def problems(kind: str, topic: str, statement: str, source_url: str, source_quote: str) -> list[str]:
    """Why a proposed update cannot be recorded, before anything is fetched."""
    out = []
    if kind not in KINDS:
        out.append(f"kind must be one of {', '.join(KINDS)}")
    if not topic_key(topic):
        out.append("topic is empty")
    if not (20 <= len((statement or "").strip()) <= 600):
        out.append("statement must be one or two sentences (20 to 600 characters)")
    if not official(source_url):
        out.append("source_url must be an official Zambian government or regulator page (not news, ZambiaLII or a law firm)")
    words = len((source_quote or "").split())
    if words < 8 or len(source_quote or "") > 1200:
        out.append("source_quote must be the exact words from the page, 8 words to 1,200 characters")
    for name, text in (("statement", statement), ("source_quote", source_quote)):
        if _PII.search(text or ""):
            out.append(f"{name} contains personal data (an e-mail, phone, NRC or account number)")
    if _PRIVATE.search(statement or ""):
        out.append("statement must state the public law, not anyone's own situation")
    return out


async def _page_text(url: str) -> str:
    from . import tools  # the fetchers live with the web tools
    fetched = await (tools._fetch_pdf_as_text(url) if url.lower().split("?")[0].endswith(".pdf")
                     else tools._web_fetch(url))
    return ((fetched or {}).get("result") or {}).get("content") or ""


async def confirm(source_url: str, source_quote: str, page_text=None) -> tuple[str, str | None]:
    """("verified" | "not_on_page" | "unreachable", content hash) for a quote on its page."""
    from .quote_check import match_score
    try:
        text = page_text if page_text is not None else await _page_text(source_url)
    except Exception:  # noqa: BLE001
        text = ""
    if len(text.strip()) < 200:
        return "unreachable", None
    digest = hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:32]
    return ("verified" if match_score(source_quote, text) >= QUOTE_MATCH else "not_on_page"), digest


def _db():
    from ..db.supabase import get_db
    return get_db()


def _today_count() -> int:
    start = datetime.now(timezone.utc).date().isoformat()
    rows = (_db().table("legal_updates").select("id", count="exact").gte("first_seen_at", start).limit(1).execute())
    return int(getattr(rows, "count", 0) or 0)


async def record(*, kind: str, topic: str, statement: str, source_url: str, source_quote: str,
                 effective_date: str | None = None, act_title: str | None = None, document_id: str | None = None,
                 value: dict | None = None, origin: str = "chat", page_text: str | None = None) -> dict:
    """Propose an update; the server checks the quote on the page before anyone sees it."""
    issues = problems(kind, topic, statement, source_url, source_quote)
    if issues:
        return {"recorded": False, "reason": "; ".join(issues)}
    status, digest = await confirm(source_url, source_quote, page_text)
    if status == "not_on_page":
        return {"recorded": False, "reason": (
            "The quote was not found on that page. Quote the page's exact words (copy them from the fetched text), "
            "or do not record the update.")}
    key = topic_key(topic)
    shash = statement_hash(statement)
    eff = None
    if effective_date:
        try:
            eff = date.fromisoformat(str(effective_date)[:10]).isoformat()
        except ValueError:
            eff = None
    now = datetime.now(timezone.utc).isoformat()

    def write() -> dict:
        db = _db()
        found = (db.table("legal_updates").select("id,status,seen_count").eq("topic", key)
                 .eq("statement_hash", shash).limit(1).execute().data)
        if found:
            row = found[0]
            patch = {"seen_count": int(row.get("seen_count") or 1) + 1, "last_checked_at": now}
            if status == "verified" and row.get("status") == "pending":
                patch.update(status="verified", verified_at=now, source_hash=digest)
            db.table("legal_updates").update(patch).eq("id", row["id"]).execute()
            return {"recorded": True, "id": row["id"], "status": patch.get("status", row.get("status")), "new": False}
        if _today_count() >= MAX_PER_DAY:
            return {"recorded": False, "reason": "today's limit on new updates is reached; try again tomorrow"}
        ins = {
            "topic": key, "kind": kind, "statement": statement.strip(), "statement_hash": shash,
            "effective_date": eff, "act_title": (act_title or "").strip()[:200] or None,
            "document_id": document_id or None, "value": value or None, "source_url": source_url.strip(),
            "source_domain": (urlparse(source_url).hostname or "").lower(), "source_quote": " ".join(source_quote.split()),
            "source_hash": digest, "status": "verified" if status == "verified" else "pending", "origin": origin,
            "last_checked_at": now, "verified_at": now if status == "verified" else None,
        }
        row = db.table("legal_updates").insert(ins).execute().data[0]
        return {"recorded": True, "id": row["id"], "status": row["status"], "new": True}

    try:
        result = await asyncio.to_thread(write)
    except Exception as e:  # noqa: BLE001
        logger.warning("legal_updates record failed: %s", e)
        return {"recorded": False, "reason": "the update store is not available"}
    _cache.clear()
    if result.get("status") == "pending":
        result["note"] = "The page could not be read just now; the update stays hidden until it is confirmed."
    return result


def active(limit: int = 60) -> list[dict]:
    """Verified and approved updates, newest first. Cached; [] on any failure."""
    hit = _cache.get("active")
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]  # type: ignore[return-value]
    try:
        rows = (_db().table("legal_updates")
                .select("id,topic,kind,statement,effective_date,act_title,document_id,value,source_url,"
                        "source_domain,source_quote,status,verified_at,last_checked_at,first_seen_at")
                .in_("status", list(SHOWN)).order("first_seen_at", desc=True).limit(limit).execute().data) or []
    except Exception:  # noqa: BLE001 — no table yet, or the database is down
        rows = []
    _cache["active"] = (time.time(), rows)
    return rows


def _when(row: dict) -> str:
    stamp = (row.get("last_checked_at") or row.get("verified_at") or row.get("first_seen_at") or "")[:10]
    try:
        d = date.fromisoformat(stamp)
        return f"{d.day} {d.strftime('%b %Y')}"
    except ValueError:
        return stamp


def prompt_block(rows: list[dict] | None = None) -> str:
    """The system-prompt list of updates, or "" when there are none."""
    rows = active() if rows is None else rows
    if not rows:
        return ""
    lines = []
    for r in rows[:PROMPT_LIMIT]:
        eff = f" (effective {r['effective_date']})" if r.get("effective_date") else ""
        mark = "" if r.get("status") == "approved" else " [checked by quote, not yet by a person]"
        lines.append(f"- {r['statement']}{eff} Source: {r['source_url']}, checked {_when(r)}.{mark}")
    return (
        "RECENT VERIFIED UPDATES: official-source facts newer than Levy's library, shared across all "
        "conversations. Where one bears on the question, prefer it over the library, cite its source and "
        "date, and say it postdates the library copy. If the user shows something newer, check it.\n"
        + "\n".join(lines))


def for_document(document_id: str | None) -> list[dict]:
    if not document_id:
        return []
    return [r for r in active() if str(r.get("document_id") or "") == str(document_id)]


def approved_value(topic: str):
    """The `value` of the newest approved row for a topic, or None."""
    key = topic_key(topic)
    for r in active():
        if r.get("topic") == key and r.get("status") == "approved" and r.get("value"):
            return r["value"], r
    return None


def review(update_id: str, status: str, note: str | None = None) -> dict:
    """A person's decision: approve, reject or supersede an update."""
    if status not in ("approved", "rejected", "superseded", "verified"):
        raise ValueError("status must be approved, rejected, superseded or verified")
    patch = {"status": status, "reviewed_at": datetime.now(timezone.utc).isoformat(), "review_note": note}
    rows = _db().table("legal_updates").update(patch).eq("id", update_id).execute().data
    _cache.clear()
    return rows[0] if rows else {}
