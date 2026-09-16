#!/usr/bin/env python3
"""Build the law map: which Acts are in force, which are repealed and by what,
which amendments belong to which principal Act, and which rules sit under it.

A user caught Levy answering from the Juveniles Act, repealed by the Children's
Code Act in 2022, even though the library stores both. Retrieval alone cannot
tell them apart, so the status travels with every search result instead.

Evidence comes from the corpus itself:
  * repeal clauses in an Act's closing sections ("... are repealed")
  * long titles ("An Act to repeal and replace the ... Act")
  * titles already annotated "[repealed by ...]" or "(Repeal) Act"
  * amendment titles ("X (Amendment) Act, 2024") pointing at their principal

Only Act-level repeals count. "Section 4 of the principal Act is repealed and
replaced" amends an Act, it does not kill it, so those are skipped.

  backend/.venv/bin/python scripts/build_law_map.py            # report only
  backend/.venv/bin/python scripts/build_law_map.py --write    # write the map
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / "backend" / ".env")
from app.db.supabase import get_db  # noqa: E402

OUT = REPO / "backend" / "app" / "data" / "law_map.json"
HEAD_CHUNKS = 2     # long title lives here
REPEAL_HITS = 8     # chunks mentioning "repeal", wherever they sit in the Act

# "... the X Act, 1956, and the Y Act, 1995 are repealed". Scans allow missing
# spaces ("arerepealed") because the corpus is OCR'd from scanned PDFs.
RE_REPEALED = re.compile(
    r"(?P<list>(?:[Tt]he\s*)?[A-Z][^.;:]{5,400}?)\s*(?:is|are)\s*(?:hereby\s*)?repealed", re.S)
# "An Act to repeal and replace the X Act"
RE_REPLACE = re.compile(
    r"repeal(?:s|ed)?\s+and\s+replace[sd]?\s+(?:the\s+)?(?P<name>[^.;:,]{5,120}?Act[^.;:,]{0,40})", re.I)
# title annotation added by an earlier harvest
RE_TITLE_REPEALED_BY = re.compile(r"\[\s*repealed\s+by\s+(?P<name>[^\]]+?)\s*\]", re.I)
# "The Tsetse Control (Repeal) Act 2010" repeals "The Tsetse Control Act"
RE_REPEAL_ACT_TITLE = re.compile(r"^(?P<stem>.+?)\s*\((?:the\s+)?repeal\)", re.I)
RE_AMENDMENT_TITLE = re.compile(r"^(?P<stem>.+?)\s*\(amendment\)", re.I)
# "Parts IV and V of the Public Health Act are repealed" kills parts of an Act,
# not the Act. Marking a live Act dead would be worse than the bug being fixed.
RE_PARTIAL = re.compile(r"\b(section|subsection|paragraph|part|parts|schedule|so much of|provisions of)\b", re.I)
NOISE = re.compile(r"^(republic of zambia|the laws of zambia|government of zambia)\s+", re.I)


MARGIN = re.compile(r"\bRepeal(?:ed)?\s+of\b|\bCap\.?\s*\d+[\d,\s and]*|\bNo\.?\s*\d+\s+of\s+\d{4}\b|\bSection\s+\d+\b", re.I)
STOP = {"act", "the", "of", "and", "zambia", "republic", "laws"}


def clean_clause(text: str) -> str:
    """Strip marginal notes the OCR spliced into the sentence, and unglue words."""
    t = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)          # "arerepealed" stays, "ActThe" splits
    t = re.sub(r"(?i)(are|is)(repealed)", r"\1 \2", t)
    t = MARGIN.sub(" ", t)
    return re.sub(r"\s+", " ", t)


def tokens(name: str) -> set[str]:
    return {w for w in norm(name).split() if w not in STOP}


def year_of(text: str) -> int | None:
    m = re.findall(r"\b(18|19|20)(\d{2})\b", text or "")
    return int(m[-1][0] + m[-1][1]) if m else None


# The scanned Acts OCR a word into two: "the Educati on Act", "Commissi on",
# "Hum an Rights", "Cred its". A repeal clause naming the "Educati on Act"
# must still match the EDUCATION ACT in the library, so the splits are sewn
# back up on both sides of the comparison. Each rule needs a stem that cannot
# stand alone as a word, so "Commission on Human Rights" is left intact.
_OCR_SPLITS = [
    (re.compile(r"\b([a-z]*(?:ti|si|ssi|zi))\s+on\b"), r"\1on"),
    (re.compile(r"\b(hum|afric|lo|germ|org)\s+an\b"), r"\1an"),
    (re.compile(r"\b(cred|benef|prof|prod|un)\s+its\b"), r"\1its"),
    (re.compile(r"\b(sm|sh|met)\s+all\b"), r"\1all"),
    (re.compile(r"\b(th|wh)\s+is\b"), r"\1is"),
    (re.compile(r"\b(f|maj|min)\s+or\b"), r"\1or"),
    (re.compile(r"\b(cott|butt|carb)\s+on\b"), r"\1on"),
    (re.compile(r"\b(st|br|dem)\s+and\b"), r"\1and"),
]


def unsplit(s: str) -> str:
    for rx, rep in _OCR_SPLITS:
        s = rx.sub(rep, s)
    return s


def norm(name: str) -> str:
    """Normalise a title for matching: drop boilerplate, case, punctuation, year."""
    s = re.sub(r"\[[^\]]*\]", " ", name or "")          # [repealed by ...]
    s = re.sub(r"\((?:cap\.?\s*\d+|no\.?\s*\d+[^)]*)\)", " ", s, flags=re.I)
    s = NOISE.sub("", s.strip())
    s = NOISE.sub("", s.strip())
    s = s.replace("’", "'")
    s = re.sub(r"\b(chapter|cap\.?)\s*\d+\b", " ", s, flags=re.I)
    s = re.sub(r"\bact\s+no\.?\s*\d+\s+of\s+\d{4}\b", " act ", s, flags=re.I)
    s = re.sub(r",?\s*(19|20)\d{2}\b", " ", s)
    s = re.sub(r"^the\s+", "", s.strip(), flags=re.I)
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    return re.sub(r"\s+", " ", unsplit(s)).strip()


def candidate_names(text: str) -> list[str]:
    """Split a repeal clause's subject list into individual Act names."""
    out = []
    for part in re.split(r",| and ", text):
        part = part.strip(" \t\n;:.")
        if not re.search(r"\bact\b", part, re.I):
            continue
        part = re.sub(r"^(?:the|and)\s+", "", part, flags=re.I)
        if 6 <= len(part) <= 140:
            out.append(part)
    return out


async def fetch_edge_chunks(docs: list[dict]) -> dict[str, str]:
    """First HEAD_CHUNKS and last TAIL_CHUNKS of each document, as one string."""
    base = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/legal_chunks"
    key = os.environ["SUPABASE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    sem = asyncio.Semaphore(8)
    out: dict[str, str] = {}

    async def one(client: httpx.AsyncClient, d: dict):
        queries = [
            {"select": "content", "document_id": f"eq.{d['id']}",
             "chunk_index": f"lt.{HEAD_CHUNKS}", "order": "chunk_index"},
            {"select": "content", "document_id": f"eq.{d['id']}",
             "content": "ilike.*repeal*", "limit": str(REPEAL_HITS)},
        ]
        parts: list[str] = []
        async with sem:
            for params in queries:
                for attempt in range(3):
                    try:
                        r = await client.get(base, params=params, headers=headers, timeout=90)
                        if r.status_code == 200:
                            parts += [c["content"] for c in r.json()]
                            break
                    except Exception:  # noqa: BLE001
                        pass
                    await asyncio.sleep(1 + attempt)
        out[d["id"]] = "\n".join(parts)

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*(one(client, d) for d in docs))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write the map file")
    args = ap.parse_args()

    db = get_db()
    docs, start = [], 0
    while True:
        rows = (db.table("legal_documents")
                .select("id,title,short_name,document_type,year,act_number,total_chunks,is_global")
                .range(start, start + 999).execute().data)
        docs += rows
        start += 1000
        if len(rows) < 1000:
            break
    by_id = {d["id"]: d for d in docs}

    # name -> ids (a normalised title can legitimately hit more than one row)
    index: dict[str, list[str]] = defaultdict(list)
    for d in docs:
        if d["document_type"] not in ("act", "court_rule"):
            continue
        for key in {norm(d["title"]), norm(d.get("short_name") or "")}:
            if len(key) > 4:
                index[key].append(d["id"])

    def doc_year(d: dict) -> int | None:
        return d.get("year") or year_of(d.get("act_number") or "") or year_of(d["title"])

    def resolve(name: str, by: dict | None = None) -> list[str]:
        """Documents a repeal clause's name refers to.

        A clause names a year ("the Employment Act, 1965"); the library often
        holds several versions of the same name, so the year picks the right
        one. An Act can only repeal something older than itself, which throws
        out the pairs where OCR pointed the arrow backwards.
        """
        key = norm(name)
        if len(key) < 5:
            return []
        hits = list(index.get(key, []))
        if not hits:
            kt = tokens(name)
            if len(kt) >= 2:
                scored = []
                for k, ids in index.items():
                    ot = {w for w in k.split() if w not in STOP}
                    if ot and len(kt & ot) / len(kt | ot) >= 0.75:
                        scored.append((len(kt & ot) / len(kt | ot), ids))
                if scored:
                    hits = list(max(scored, key=lambda x: x[0])[1])
        if by:
            by_y = doc_year(by)
            hits = [h for h in hits if h != by["id"]
                    and not (by_y and doc_year(by_id[h]) and doc_year(by_id[h]) >= by_y)]
        want = year_of(name)
        if want and len(hits) > 1:
            exact = [h for h in hits if doc_year(by_id[h]) == want]
            if exact:
                return exact
        return hits

    scan = [d for d in docs if d["document_type"] in ("act", "court_rule")]
    print(f"documents {len(docs)} | scanning {len(scan)} acts and rules for repeal clauses", flush=True)
    text = asyncio.run(fetch_edge_chunks(scan))
    print(f"fetched edge text for {len(text)} documents", flush=True)

    repeals: list[dict] = []          # {by, target_id|None, name, evidence}
    amends: list[dict] = []
    unresolved: list[dict] = []

    for d in scan:
        body = clean_clause(text.get(d["id"], ""))
        found: list[tuple[str, str]] = []
        for m in RE_REPEALED.finditer(body):
            clause = m.group("list")
            partial = bool(RE_PARTIAL.search(clause))
            for nm in candidate_names(clause):
                found.append((nm, re.sub(r"\s+", " ", m.group(0))[:200], partial))
        for m in RE_REPLACE.finditer(body):
            found.append((m.group("name"), re.sub(r"\s+", " ", m.group(0))[:200], False))
        for nm, ev, partial in found:
            ids = resolve(nm, by=d)
            if ids:
                for tid in ids:
                    repeals.append({"by": d["id"], "target": tid, "name": nm.strip(),
                                    "evidence": ev, "partial": partial})
            else:
                unresolved.append({"by": d["id"], "name": nm.strip(), "evidence": ev})

        # title annotations
        m = RE_TITLE_REPEALED_BY.search(d["title"])
        if m:
            for tid in resolve(m.group("name")) or [None]:
                repeals.append({"by": tid, "target": d["id"], "name": m.group("name").strip(),
                                "evidence": "title annotation"})
        m = RE_REPEAL_ACT_TITLE.match(re.sub(r"\[[^\]]*\]", "", d["title"]))
        if m and "amendment" not in d["title"].lower():
            for tid in resolve(m.group("stem") + " Act", by=d):
                repeals.append({"by": d["id"], "target": tid, "name": m.group("stem").strip(),
                                "evidence": "(Repeal) Act title"})
        m = RE_AMENDMENT_TITLE.match(d["title"])
        if m:
            for pid in resolve(m.group("stem") + " Act", by=None):
                if "(amendment)" in by_id[pid]["title"].lower():
                    continue    # an amendment does not amend another amendment
                amends.append({"by": d["id"], "target": pid})

    # ---- assemble ----
    entry: dict[str, dict] = {}

    def slot(doc_id: str) -> dict:
        return entry.setdefault(doc_id, {"status": "in force", "repealed_by": [], "repeals": [],
                                         "partially_repealed_by": [], "amended_by": [], "amends": [],
                                         "enacted_as": []})

    def add(items: list[dict], item: dict) -> None:
        if not any(x.get("id") == item.get("id") and x.get("title") == item.get("title") for x in items):
            items.append(item)

    for r in repeals:
        t = slot(r["target"])
        by = by_id.get(r["by"]) if r["by"] else None
        note = {"title": (by or {}).get("title", r["name"]), "id": r["by"], "evidence": r["evidence"][:160]}
        if r.get("partial"):
            add(t["partially_repealed_by"], note)
            continue
        t["status"] = "repealed"
        add(t["repealed_by"], note)
        if r["by"]:
            add(slot(r["by"])["repeals"], {"title": by_id[r["target"]]["title"], "id": r["target"]})
    for a in amends:
        add(slot(a["target"])["amended_by"], {"title": by_id[a["by"]]["title"], "id": a["by"]})
        add(slot(a["by"])["amends"], {"title": by_id[a["target"]]["title"], "id": a["target"]})
        if slot(a["by"])["status"] == "in force":
            slot(a["by"])["status"] = "amending Act"
    # A bill whose Act is now in the library has passed. Left alone it would be
    # announced as "not yet law", which is the same error in the other
    # direction.
    act_names = {norm(d["title"]): d for d in docs if d["document_type"] == "act"}
    for d in docs:
        if d["document_type"] != "bill":
            continue
        as_act = act_names.get(norm(re.sub(r"\bbill\b", "Act", d["title"], flags=re.I)))
        # Same name is not enough: "The Land (Perpetual Succession) Bill" would
        # match the old Act of that name. The Act must carry the bill's year.
        bill_year = year_of(d["title"])
        if as_act and bill_year and year_of(as_act["title"]) != bill_year and as_act.get("year") != bill_year:
            as_act = None
        e = slot(d["id"])
        if as_act:
            e["status"] = "enacted"
            add(e["enacted_as"], {"title": as_act["title"], "id": as_act["id"]})
        else:
            e["status"] = "bill, not yet law"

    partial = [i for i, e in entry.items() if e["partially_repealed_by"] and e["status"] != "repealed"]
    repealed = [i for i, e in entry.items() if e["status"] == "repealed"]
    print(f"\nPARTIALLY REPEALED (still in force): {len(partial)}")
    for i in partial:
        print(f"  {by_id[i]['title'][:58]:60} parts repealed by "
              f"{', '.join(x['title'][:34] for x in entry[i]['partially_repealed_by'])}")
    print(f"\nREPEALED ACTS FOUND: {len(repealed)}")
    for i in repealed:
        e = entry[i]
        print(f"  {by_id[i]['title'][:62]:64} <- {', '.join(x['title'][:40] for x in e['repealed_by'])}")
        print(f"      evidence: {e['repealed_by'][0]['evidence'][:120]}")
    enacted = [i for i, e in entry.items() if e["status"] == "enacted"]
    print(f"\nBILLS SINCE ENACTED (no longer 'not yet law'): {len(enacted)}")
    for i in enacted[:8]:
        print(f"  {by_id[i]['title'][:56]:58} -> {entry[i]['enacted_as'][0]['title'][:44]}")
    print(f"\nAMENDMENT LINKS: {len(amends)} (principals with amendments: "
          f"{len({a['target'] for a in amends})})")
    for pid in list({a['target'] for a in amends})[:8]:
        print(f"  {by_id[pid]['title'][:60]:62} <- {len(entry[pid]['amended_by'])} amendment(s)")
    print(f"\nUNRESOLVED repeal mentions (named Act not in the library): {len(unresolved)}")
    for u in unresolved[:10]:
        print(f"  {by_id[u['by']]['title'][:45]:47} says repealed: {u['name'][:60]}")

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "documents": entry,
            "unresolved": unresolved[:200],
        }, indent=1))
        print(f"\nwrote {OUT} ({OUT.stat().st_size // 1024} KB, {len(entry)} documents)")
    else:
        print("\n(report only; pass --write to save the map)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
