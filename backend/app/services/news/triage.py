"""Group new headlines into stories and pick the claims worth checking.

One Haiku 5.5 call per batch of up to 50 headlines, with structured output.
Sorting 200 headlines costs about a cent. New items join a recent story
when they report the same event or claim; otherwise they start a new one.
"""
from __future__ import annotations

import json

from .costs import HAIKU, RunBudget

CATEGORIES = ["government", "money", "jobs_scams", "health", "elections", "crime_security", "other"]
RISKS = ["named_person", "election", "court_case", "health", "violence", "ethnicity"]
BATCH = 50              # a longer batch's answer can run past max_tokens and arrive cut off

SYSTEM = """You sort Zambian news into stories for Levy News, which checks claims against official records and reliable reporting.

You get recent stories (refs S1, S2, ...) and new items (refs I1, I2, ...) from Zambian outlets, Google News, Reddit and fact-checkers. Assign every new item to an existing story when it reports the same event or claim. Otherwise assign it to a new story (keys N1, N2, ...). Several new items can share a new story.

For each new story give:
- title: a short, neutral working title.
- claim: the single most checkable factual claim at its centre, written neutrally as a statement, for example "The Bank of Zambia will stop accepting K50 notes from Friday". Leave it empty when there is no checkable claim: opinion, sport results, or a routine announcement nobody disputes.
- check_worthy: 0 for no checkable claim; 1 for factual but routine and undisputed; 2 for a specific claim people may doubt or that could mislead; 3 for a viral rumour, a disputed or surprising claim, or a possible hoax, scam or fake notice. Levy News checks claims about Zambia or that affect people in Zambia: a story about another country with no Zambian angle is 0, however viral.
- category: government, money, jobs_scams, health, elections, crime_security, or other.
- risks: list only those that apply, otherwise an empty list. named_person if it alleges wrongdoing, illness, death or scandal about an identifiable person; election if it concerns voting, results, candidates or campaigns; court_case if it concerns a case before a court; health for medical or public-health claims; violence for attacks, unrest or deaths; ethnicity if it concerns a tribe, region or ethnic group.

Keep titles under 12 words and claims to one sentence.

Items from fact-checkers are a sign that a claim is circulating; put them with the story they check."""

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["assignments", "new_stories"],
    "properties": {
        "assignments": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["item", "story"],
            "properties": {"item": {"type": "string"}, "story": {"type": "string"}}}},
        "new_stories": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["key", "title", "claim", "check_worthy", "category", "risks"],
            "properties": {
                "key": {"type": "string"}, "title": {"type": "string"}, "claim": {"type": "string"},
                "check_worthy": {"type": "integer"},
                "category": {"type": "string", "enum": CATEGORIES},
                "risks": {"type": "array", "items": {"type": "string", "enum": RISKS}},
            }}},
    },
}


def _prompt(items: list[dict], stories: list[dict]) -> str:
    lines = ["Recent stories:"] + [f"S{i}. {s['title']}" + (f" | claim: {s['claim']}" if s.get("claim") else "")
                                   for i, s in enumerate(stories, 1)]
    if not stories:
        lines.append("(none)")
    lines += ["", "New items:"]
    for i, it in enumerate(items, 1):
        summary = f" | {it['summary'][:160]}" if it.get("summary") else ""
        lines.append(f"I{i}. [{it['outlet']}, {it['outlet_type']}] {it['title']}{summary}")
    return "\n".join(lines)


def read_result(raw: dict, items: list[dict], stories: list[dict]) -> tuple[dict, list[dict]]:
    """Map refs back to records: {item index: story id or new key} and the new stories.

    An item the model left out, or pointed at an unknown ref, starts a story of its
    own with check_worthy 0, so nothing is silently dropped or misfiled."""
    new = {s["key"]: {**s, "check_worthy": max(0, min(3, int(s.get("check_worthy", 0)))),
                      "category": s.get("category") if s.get("category") in CATEGORIES else "other",
                      "risk": {r: r in (s.get("risks") or []) for r in RISKS}}
           for s in raw.get("new_stories", [])}
    where: dict[int, str] = {}
    for a in raw.get("assignments", []):
        ref, target = a.get("item", ""), a.get("story", "")
        if not ref.startswith("I") or not ref[1:].isdigit():
            continue
        idx = int(ref[1:]) - 1
        if not 0 <= idx < len(items):
            continue
        if target.startswith("S") and target[1:].isdigit() and 0 < int(target[1:]) <= len(stories):
            where[idx] = stories[int(target[1:]) - 1]["id"]
        elif target in new:
            where[idx] = target
    for idx in range(len(items)):
        if idx not in where:
            key = f"orphan-{idx}"
            new[key] = {"key": key, "title": items[idx]["title"], "claim": "", "check_worthy": 0,
                        "category": "other", "risk": {r: False for r in RISKS}}
            where[idx] = key
    return where, [s for k, s in new.items() if k in set(where.values())]


def _sort(client, budget: RunBudget, chunk: list[dict], stories: list[dict]) -> dict:
    """The model's answer for one batch. An answer cut off at max_tokens is
    retried as two half batches, merged with item refs renumbered."""
    budget.reserve(0.05)
    try:
        resp = client.messages.create(
            model=HAIKU, max_tokens=16000, system=SYSTEM,
            messages=[{"role": "user", "content": _prompt(chunk, stories)}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}})
    finally:
        budget.release(0.05)
    budget.add(HAIKU, resp.usage, "triage")
    if resp.stop_reason == "max_tokens" and len(chunk) > 1:
        half = len(chunk) // 2
        a, b = _sort(client, budget, chunk[:half], stories), _sort(client, budget, chunk[half:], stories)
        shift = lambda ref: f"I{int(ref[1:]) + half}" if ref.startswith("I") and ref[1:].isdigit() else ref  # noqa: E731
        rekey = lambda key: f"B{key}" if key.startswith("N") else key  # noqa: E731
        return {"assignments": a["assignments"] + [{"item": shift(x["item"]), "story": rekey(x["story"])} for x in b["assignments"]],
                "new_stories": a["new_stories"] + [{**s, "key": rekey(s["key"])} for s in b["new_stories"]]}
    return json.loads("".join(b.text for b in resp.content if b.type == "text"))


def triage(client, budget: RunBudget, items: list[dict], stories: list[dict]) -> tuple[dict, list[dict]]:
    """Assignments for `items` (by index) and the new stories they create, batch by batch.

    Each batch also sees the stories the batches before it created, so one event
    split across two batches still becomes one story."""
    where: dict[int, str] = {}
    new_all: list[dict] = []
    known = list(stories)
    for start in range(0, len(items), BATCH):
        chunk = items[start:start + BATCH]
        w, new = read_result(_sort(client, budget, chunk, known), chunk, known)
        prefix = f"b{start}-"                       # keys are only unique within a batch
        new_keys = {s["key"] for s in new}
        for idx, target in w.items():
            where[start + idx] = prefix + target if target in new_keys else target
        made = [{**s, "key": prefix + s["key"]} for s in new]
        new_all += made
        known += [{"id": s["key"], "title": s["title"], "claim": s.get("claim")} for s in made if not s["key"].split("-", 1)[1].startswith("orphan")]
    return where, new_all
