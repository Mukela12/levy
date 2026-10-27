"""Check one story's claim: gather evidence, test the quotes, write the verdict.

The setup is the one the 27 Oct 2026 pilot chose (~/levy-research/news-pilot/
RESULTS.md):
- Haiku 5.5 gathers evidence with web search and fetch, about $0.06 a claim.
  Gathering with Sonnet was no better.
- One Sonnet 5.5 call judges it, about half a cent. Five calls were no better
  than one.
- The verdict instructions are the GEPA-tuned prompt (held-out accuracy 61% to
  65%; no false or misleading claim was ever rated True), plus a guard the
  tuning lacked: a claim under 48 hours old is not False just because no one
  has reported it yet.

Every quote in the evidence is looked up on its page with Levy's quote matcher
before the check is stored, and anything risky waits for the editor.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import re
from datetime import datetime, timedelta, timezone

import httpx

from ..quote_check import CLOSE, match_score
from ..watcher import BROWSER_UA, html_text
from .costs import HAIKU, SONNET, RunBudget

LABELS = ["True", "Misleading", "False", "Unproven"]
BLOCKED = ["zambialii.org"]          # Levy never scrapes ZambiaLII; official sources instead
EVIDENCE_RESERVE, VERDICT_RESERVE = 0.15, 0.05     # pilot: evidence median $0.05, 95th percentile $0.13
RECENT_HOURS = 48

EVIDENCE_SYSTEM = """You gather evidence about a claim circulating in Zambia, for Levy News, which publishes a fact-check only after an editor has reviewed it.

Look for the most authoritative sources first: official Zambian bodies (ministries, State House, the Bank of Zambia, ZRA, Parliament, the Judiciary, the Electoral Commission of Zambia, ZNPHI, the Government Gazette), then established news outlets, then primary documents and data. If an established fact-checker such as iVerify Zambia, Africa Check, AFP Fact Check or PesaCheck has checked the same claim, include their check as a source. The reports listed with the claim are a place to start. Note when a source is much later or earlier than the claim. Include evidence that cuts both ways, and say plainly when you could not find something.

Do not give a verdict. End your reply with the dossier as JSON inside <dossier></dossier> tags:
{"summary": "two or three sentences on what the evidence shows and what is missing",
 "sources": [{"url": "...", "publisher": "...", "date": "YYYY-MM-DD or unknown", "source_type": "official|news|social|document|fact_check|other",
              "quote": "a verbatim excerpt under 40 words that bears on the claim", "stance": "supports|contradicts|neutral"}]}"""

DOSSIER_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["summary", "sources"],
    "properties": {
        "summary": {"type": "string"},
        "sources": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["url", "publisher", "date", "source_type", "quote", "stance"],
            "properties": {
                "url": {"type": "string"}, "publisher": {"type": "string"}, "date": {"type": "string"},
                "source_type": {"type": "string", "enum": ["official", "news", "social", "document", "fact_check", "other"]},
                "quote": {"type": "string"}, "stance": {"type": "string", "enum": ["supports", "contradicts", "neutral"]},
            }}},
    },
}

# The GEPA-tuned instructions (news-pilot/gepa/sonnet, candidate 1), then rule 6
# and the writing rules, which are new.
VERDICT_SYSTEM = """You judge claims that circulated in Zambia, using only the evidence dossier you are given.

Labels:
- True: the evidence supports the claim as stated.
- Misleading: has a real basis but is exaggerated, distorted, or missing context that changes its meaning.
- False: the evidence contradicts the claim, or shows the described event did not happen as claimed.
- Unproven: the evidence is too thin or too evenly split to judge, and the claim is not the kind that would leave a public record if true.

How to decide:

1. Published fact-checks. If the dossier reports a verdict by an established fact-checking organisation on the same claim, adopt its label unless the dossier holds stronger, more specific evidence pointing elsewhere. Map "misleading", "exaggerated", "partly false" or "lacks context" to Misleading. Map "false", "fabricated" or "did not happen" to False. Do not turn a fact-checker's "misleading" into False because the claim looks weak to you.

2. Exaggerated claims with a real basis. Sometimes the subject is real and some underlying fact is genuine, such as an existing product, limited testing, or an actual incident, but the claim inflates it into miracle results, official approval or large numbers. Label these Misleading. Reserve False for claims whose core is directly contradicted or invented.

3. Absence of evidence. Ask whether the claim, if true, would have been widely reported. Specific, dramatic, checkable events leave traces in news and official sources. Examples are deaths, disasters, arrests and government announcements. Searches may find coverage of similar events but no record of the claimed one. Treat that as evidence the claim is false, not as Unproven. Use Unproven for claims that would not necessarily be recorded, such as private remarks, minor local matters or predictions, or where credible evidence conflicts. Incomplete searching should lower your confidence, not change the label.

4. Old claims. Claims from earlier years have often already been checked. Judge them against what was true when they circulated, and give weight to dated verdicts.

5. True requires direct support for the claim as stated, including its numbers, dates and qualifiers. Partial support is at best Misleading. Never rate a claim True because nothing contradicts it.

6. Breaking claims. If the claim first appeared less than 48 hours ago, a lack of reports is not yet evidence either way: use Unproven unless a source directly contradicts or confirms it.

Confidence is your estimate, from 0 to 100, that an experienced fact-checker would give the same label. Use higher values when a published fact-check or direct official evidence settles the question. Use moderate values when the label rests on missing records or limited searches. Keep the reasoning under 120 words.

Then write the check for readers, in plain and careful English:
- headline: says what is true, in under 14 words, without repeating a false claim as if it were fact.
- claim: what was claimed, in one neutral sentence.
- verdict_text: the verdict in one or two sentences.
- what_we_found: two to four short paragraphs, separated by blank lines, naming the sources. Cite a source by its number in brackets, like [2].
- case_for and case_against: the strongest points on each side, two to four each.
- would_change: what new evidence would change the verdict.
Do not use em dashes. Describe allegations about people neutrally, and never repeat insults or slurs."""

VERDICT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["label", "confidence", "reasoning", "headline", "claim", "verdict_text", "what_we_found",
                 "case_for", "case_against", "would_change"],
    "properties": {
        "label": {"type": "string", "enum": LABELS},
        "confidence": {"type": "integer"},
        "reasoning": {"type": "string"},
        "headline": {"type": "string"},
        "claim": {"type": "string"},
        "verdict_text": {"type": "string"},
        "what_we_found": {"type": "string"},
        "case_for": {"type": "array", "items": {"type": "string"}},
        "case_against": {"type": "array", "items": {"type": "string"}},
        "would_change": {"type": "string"},
    },
}


def _text(content) -> str:
    return "".join(getattr(b, "text", "") for b in content if getattr(b, "type", "") == "text")


def gather_evidence(client, budget: RunBudget, claim: str, first_seen: str, reports: list[dict]) -> dict:
    listed = "\n".join(f"- {r['outlet']}: {r['title']} ({r['url']})" for r in reports[:8])
    user = f"Claim (first seen {first_seen[:10]}):\n{claim}\n\nReports that carried it:\n{listed or '(none)'}"
    tools = [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 5, "blocked_domains": BLOCKED},
        {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 3, "blocked_domains": BLOCKED},
    ]
    messages = [{"role": "user", "content": user}]
    cost = 0.0
    budget.reserve(EVIDENCE_RESERVE)
    try:
        for _ in range(4):                       # the first call, then up to three pause_turn resumes
            resp = client.messages.create(model=HAIKU, max_tokens=12000, system=EVIDENCE_SYSTEM, messages=messages,
                                          tools=tools, output_config={"effort": "medium"})
            cost += budget.add(HAIKU, resp.usage, "evidence")
            if resp.stop_reason != "pause_turn":
                break
            messages = [{"role": "user", "content": user}, {"role": "assistant", "content": resp.content}]
    finally:
        budget.release(EVIDENCE_RESERVE)
    raw = _text(resp.content)
    m = re.search(r"<dossier>\s*(\{.*\})\s*</dossier>", raw, re.S)
    try:
        dossier = json.loads(m.group(1)) if m else None
    except json.JSONDecodeError:
        dossier = None
    if dossier is None:                          # one cheap repair pass with a strict schema
        fix = client.messages.create(
            model=HAIKU, max_tokens=6000,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": DOSSIER_SCHEMA}},
            messages=[{"role": "user", "content": "Turn this research note into the dossier JSON. Keep URLs and quotes "
                                                  "exactly as written.\n\n" + raw[-20000:]}])
        cost += budget.add(HAIKU, fix.usage, "dossier_repair")
        dossier = json.loads(_text(fix.content))
    dossier.setdefault("sources", [])
    dossier.setdefault("summary", "")
    return {"dossier": dossier, "cost": cost}


def _page_text(url: str) -> str | None:
    """The page's text, or None when it cannot be read (blocked, login wall, error)."""
    headers = {"User-Agent": BROWSER_UA, "Accept": "text/html,application/pdf,*/*"}
    for verify in (True, False):
        try:
            r = httpx.get(url, timeout=20, follow_redirects=True, headers=headers, verify=verify)
            break
        except httpx.ConnectError as e:
            if verify and "CERTIFICATE_VERIFY_FAILED" in str(e):
                continue                          # gov.zm sites with an incomplete chain
            return None
        except httpx.HTTPError:
            return None
    else:
        return None
    if r.status_code >= 400:
        return None
    if "pdf" in r.headers.get("content-type", "") or url.lower().split("?")[0].endswith(".pdf"):
        try:
            import pymupdf
            with pymupdf.open(stream=r.content, filetype="pdf") as doc:
                return " ".join(page.get_text() for page in doc)
        except Exception:  # noqa: BLE001
            return None
    return html_text(r.text)


def check_quotes(sources: list[dict], fetch=None) -> list[dict]:
    """Mark each source's quote found (True), not on the page (False) or unreadable (None)."""
    fetch = fetch or _page_text

    def one(s: dict):
        url = s.get("url", "")
        if not url.startswith("http") or "zambialii.org" in url or s.get("source_type") == "social":
            return None
        text = fetch(url)
        if text is None:
            return None
        return match_score(s.get("quote", ""), text) >= CLOSE
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        found = list(pool.map(one, sources))
    return [{**s, "quote_found": f} for s, f in zip(sources, found)]


def judge(client, budget: RunBudget, claim: str, first_seen: str, dossier: dict) -> dict:
    lines = [f"Evidence summary: {dossier.get('summary', '')}", "", "Sources:"]
    for i, s in enumerate(dossier.get("sources") or [], 1):
        lines.append(f"{i}. [{s.get('source_type')}, {s.get('stance')}] {s.get('publisher')} ({s.get('date')}) "
                     f"{s.get('url')}\n   \"{s.get('quote')}\"")
    if not dossier.get("sources"):
        lines.append("(none found)")
    user = f"Claim (first seen {first_seen[:10]}):\n{claim}\n\n" + "\n".join(lines) + "\n\nWeigh the evidence and give your verdict."
    budget.reserve(VERDICT_RESERVE)
    try:
        resp = client.messages.create(
            model=SONNET, max_tokens=8000, system=VERDICT_SYSTEM, messages=[{"role": "user", "content": user}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": VERDICT_SCHEMA}})
    finally:
        budget.release(VERDICT_RESERVE)
    cost = budget.add(SONNET, resp.usage, "verdict")
    if resp.stop_reason != "end_turn":
        raise RuntimeError(f"verdict stopped: {resp.stop_reason}")
    v = json.loads(_text(resp.content))
    v["confidence"] = max(0, min(100, int(v["confidence"])))
    return {"verdict": v, "cost": cost}


def apply_guards(verdict: dict, sources: list[dict], first_seen: str, risk: dict, now: datetime | None = None) -> dict:
    """The rules the model cannot be trusted to keep, applied in code.

    - Breaking claims: under 48 hours old and rated False with no source that
      contradicts it means "not reported yet", so Unproven, re-checked tomorrow.
    - Risky stories (named people, elections, courts, health, violence,
      ethnicity) are held for the editor, and a verdict against a named person
      needs a right of reply first.
    - A quote that is not on its page, or no evidence at all, is flagged.
    """
    now = now or datetime.now(timezone.utc)
    v = dict(verdict)
    flags: list[str] = []
    recheck = None
    seen = datetime.fromisoformat(first_seen) if first_seen else now
    age = (now - seen).total_seconds() / 3600
    contradicting = [s for s in sources if s.get("stance") == "contradicts"
                     and s.get("source_type") in ("official", "news", "document", "fact_check")]
    if age < RECENT_HOURS and v["label"] == "False" and not contradicting:
        v["label"] = "Unproven"
        flags.append("recent_no_contradiction")
        recheck = now + timedelta(hours=24)
    if v["label"] == "Unproven" and recheck is None:
        recheck = now + timedelta(hours=72)
    risky = [k for k, on in (risk or {}).items() if on]
    flags += [f"risk:{k}" for k in risky]
    if (risk or {}).get("named_person") and v["label"] in ("False", "Misleading"):
        flags.append("right_of_reply")
    missing = [str(i) for i, s in enumerate(sources, 1) if s.get("quote_found") is False]
    if missing:
        flags.append("quote_not_found:" + ",".join(missing))
    if not sources:
        flags.append("no_evidence")
    return {"verdict": v, "flags": flags, "review_status": "held" if risky else "pending",
            "recheck_at": recheck.isoformat() if recheck else None}


def check_story(client, budget: RunBudget, story: dict, reports: list[dict]) -> dict:
    """A news_checks row for the story's claim."""
    first_seen = story.get("first_seen_at") or datetime.now(timezone.utc).isoformat()
    ev = gather_evidence(client, budget, story["claim"], first_seen, reports)
    sources = check_quotes(ev["dossier"]["sources"])
    jv = judge(client, budget, story["claim"], first_seen, {**ev["dossier"], "sources": sources})
    g = apply_guards(jv["verdict"], sources, first_seen, story.get("risk") or {})
    v = g["verdict"]
    return {
        "story_id": story["id"], "label": v["label"], "confidence": v["confidence"], "headline": v["headline"],
        "claim": v["claim"] or story["claim"], "verdict_text": v["verdict_text"], "what_we_found": v["what_we_found"],
        "case_for": v["case_for"], "case_against": v["case_against"], "would_change": v["would_change"],
        "evidence": sources, "evidence_summary": ev["dossier"].get("summary", ""), "flags": g["flags"],
        "review_status": g["review_status"], "recheck_at": g["recheck_at"],
        "models": {"evidence": HAIKU, "verdict": SONNET, "reasoning": v.get("reasoning", "")},
        "cost_usd": round(ev["cost"] + jv["cost"], 4),
    }
