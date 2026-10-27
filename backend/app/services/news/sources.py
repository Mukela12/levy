"""Where Levy News finds stories: outlet feeds, Google News, r/Zambia and iVerify.

Feeds are read directly. On 26 Oct 2026 no paid news API covered Zambian outlets
well, while the outlets' own RSS and a Google News search did. RSS and Atom both
parse with the standard library. A Google News item names its real outlet in
<source>, which is mapped to an ownership type, so coverage can be shown as
state-owned, private or social media rather than a left-right scale.
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import html
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

logger = logging.getLogger(__name__)

SOURCES = Path(__file__).resolve().parents[2] / "data" / "news_sources.json"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130.0 Safari/537.36")
ATOM = "{http://www.w3.org/2005/Atom}"

# ZNBC, the Daily Mail and the Times of Zambia are state-owned (State Media Monitor).
STATE_OWNED = ("znbc", "daily mail", "daily-mail.co.zm", "times of zambia", "times.co.zm")
SOCIAL = ("facebook", "tiktok", "twitter", "x.com", "youtube", "instagram", "reddit", "whatsapp", "threads")
FACT_CHECKERS = ("iverify", "africa check", "africacheck", "pesacheck", "afp fact", "makanday", "aca zambia")
OFFICIAL = (".gov.zm", "zra.org.zm", "boz.zm", "parliament.gov.zm", "judiciaryzambia.com", "elections.org.zm")
TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|amp$)")


def outlet_type(name: str, url: str = "") -> str:
    hay = f"{name} {url}".lower()
    if any(s in hay for s in FACT_CHECKERS):
        return "fact_checker"
    if any(s in hay for s in SOCIAL):
        return "social"
    if any(s in hay for s in STATE_OWNED):
        return "state"
    if any(s in hay for s in OFFICIAL):
        return "official"
    return "private"


def normalize_url(url: str) -> str:
    """One spelling per article: https, lower-case host, no tracking tags or fragment."""
    p = urlparse((url or "").strip())
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k.lower())])
    path = p.path.rstrip("/") or "/"
    return urlunparse(("https", host, path, "", query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode()).hexdigest()


def clean_text(raw: str, limit: int = 400) -> str:
    t = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw or ""))
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit]


def _when(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        d = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).isoformat()


def parse_feed(xml_text: str, feed: dict) -> list[dict]:
    """Items from an RSS 2.0 or Atom document; unparseable feeds give none."""
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError:
        return []
    out = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        title = clean_text(it.findtext("title") or "", 300)
        if not link or not title:
            continue
        src = it.find("source")
        outlet = (src.text or "").strip() if src is not None and src.text else feed["name"]
        otype = outlet_type(outlet, src.get("url", "") if src is not None else "") if src is not None else feed["type"]
        if src is not None and feed["type"] == "aggregator":
            title = re.sub(r"\s+-\s+" + re.escape(outlet) + r"\s*$", "", title)   # Google appends "- Outlet"
        out.append({"url": link, "title": title, "summary": clean_text(it.findtext("description") or ""),
                    "published_at": _when(it.findtext("pubDate")), "outlet": outlet, "outlet_type": otype,
                    "feed": feed["name"]})
    for e in root.iter(f"{ATOM}entry"):
        link_el = e.find(f"{ATOM}link")
        link = link_el.get("href", "") if link_el is not None else ""
        title = clean_text(e.findtext(f"{ATOM}title") or "", 300)
        if not link or not title:
            continue
        out.append({"url": link, "title": title,
                    "summary": clean_text(e.findtext(f"{ATOM}content") or e.findtext(f"{ATOM}summary") or ""),
                    "published_at": _when(e.findtext(f"{ATOM}published") or e.findtext(f"{ATOM}updated")),
                    "outlet": feed["name"], "outlet_type": feed["type"], "feed": feed["name"]})
    return out


def fetch(url: str) -> str:
    headers = {"User-Agent": BROWSER_UA, "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*"}
    for verify in (True, False):
        # Some Zambian sites omit their intermediate certificate, which browsers
        # repair and Python does not; the second try reads the feed anyway.
        try:
            r = httpx.get(url, timeout=30.0, follow_redirects=True, headers=headers, verify=verify)
            return r.text if r.status_code == 200 else ""
        except httpx.ConnectError:
            if not verify:
                return ""
        except httpx.HTTPError:
            return ""
    return ""


def load_sources() -> list[dict]:
    return json.loads(SOURCES.read_text())


def collect(sources: list[dict] | None = None, since_hours: float = 36, fetcher=fetch) -> list[dict]:
    """New-enough items from every feed, one per URL."""
    sources = sources if sources is not None else load_sources()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        pages = list(pool.map(lambda s: fetcher(s["url"]), sources))
    seen, items = set(), []
    for feed, page in zip(sources, pages):
        parsed = parse_feed(page, feed) if page else []
        if not parsed:
            logger.warning("news feed gave no items: %s", feed["name"])
        for it in parsed:
            if it["published_at"] and datetime.fromisoformat(it["published_at"]) < cutoff:
                continue
            h = url_hash(it["url"])
            if h in seen:
                continue
            seen.add(h)
            items.append({**it, "url_hash": h})
    return items
