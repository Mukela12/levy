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
import tempfile
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
REPEAL_HITS = 12    # chunks with a repeal clause or long title, then any "repeal" mention

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
# "This Act shall come into operation on such date as the Minister may, by
# statutory instrument, appoint." Passed is not the same as in force: the
# National Pension Scheme Act, 2026 repeals Cap. 256 but had no commencement
# order in September 2026, so Cap. 256 was still the law.
# Matched with all whitespace removed, so OCR spacing ("come in to operati on")
# cannot hide it.
RE_DEFERRED = re.compile(
    # "on such date as the Minister may, by statutory instrument, appoint",
    # "on the date appointed by the President by statutory instrument". The
    # authority varies, and spliced margin notes land anywhere in the sentence
    # ("on commence- the date", "by commence- statutory instrument"), so any
    # "date ... appoint ... statutory instrument" sentence counts. "The date
    # of publication" and "the date of assent" do not.
    r"comeinto(?:operation|force)on[^.]{0,14}?(?:such|the|a)?date(?!of)(?=[^.]{0,90}?appoint)"
    r"[^.]{0,80}?statutoryinstrument",
    re.I)
# A deferred-commencement Act older than this is assumed to have started; the
# library holds no commencement orders to say otherwise.
PENDING_FROM_YEAR = 2025
# Parliament's undated "Chapter" texts come from the 1995 revised edition,
# consolidated to about 1996.
UNDATED_EDITION_YEAR = 1996


MARGIN = re.compile(r"\bRepeal(?:ed)?\s+of\b|\bCap\.?\s*\d+[\d,\s and]*|\bNo\.?\s*\d+\s+of\s+\d{4}\b|\bSection\s+\d+\b", re.I)
STOP = {"act", "the", "of", "and", "zambia", "republic", "laws"}


def clean_clause(text: str) -> str:
    """Strip marginal notes the OCR spliced into the sentence, and unglue words."""
    t = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)          # "arerepealed" stays, "ActThe" splits
    t = re.sub(r"(?i)(are|is)(repealed)", r"\1 \2", t)
    # "Act No.22 of the Public Health Act ... are repealed": the full stop in
    # "No." ended the clause there and lost "sections 79 and 83 of".
    t = re.sub(r"\b(No|Nos|Cap|Caps)\.\s*(?=\d)", r"\1 ", t)
    t = MARGIN.sub(" ", t)
    # Margin Chapter numbers spliced into a name: "the Minimum Wages and
    # Conditions of 270,274and 276 Employment Act,1982" (Employment Code Act,
    # s. 137). Left in, the Act never matched and read as still in force.
    t = re.sub(r"\b\d{2,3}(?:\s*,\s*\d{2,3})*\s*and\s*\d{2,3}\b(?!\s*of\b)", " ", t)
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


# "sections 79 and 83 of the Public Health Act": OCR glues the words
# ("andsections79and83"), so no word boundary in front.
RE_PART_OF = re.compile(r"(?:sub)?sections?\s*\(?\d|paragraphs?\s*\(?\d|parts?\s*[IVX\d]+\b"
                        r"|schedules?\s*[IVX\d]*\s*to|schedules?\s*[IVX\d]|so\s*much\s*of|provisions\s*of", re.I)


def candidate_parts(text: str) -> list[tuple[str, bool]]:
    """Split a repeal clause's subject list into (Act name, partial) pairs.

    Names end at "Act"; splitting on every " and " cut "the Minimum Wages and
    Conditions of Employment Act" down to "Conditions of Employment Act", so
    the list is cut after each "Act" instead and the joiners are peeled off.
    Partial is decided per name: in "The Food and Drugs Act, 1972 and sections
    79 and 83 of the Public Health Act, 1930 are repealed" only the Public
    Health Act is partly repealed. A section reference cut off from its Act
    by a spliced margin note carries over to the next name.
    """
    out: list[tuple[str, bool]] = []
    carry = False
    for seg in re.findall(r".*?\b(?:Act|Code)\b(?!\s*Act)", text, flags=re.S | re.I):
        part = seg.strip(" \t\n;:.")
        marker = None
        for marker in RE_PART_OF.finditer(part):
            pass
        partial = carry
        if marker:
            partial = True
            tail = part[marker.end():]
            if re.search(r"(?:of|to)$", marker.group(0), re.I):
                part = tail                      # "so much of the X Act"
            else:                                # "sections 79 and 83 of the X Act"
                of = list(re.finditer(r"\b(?:of|to)\s+(?:the\s+)?", tail, re.I))
                part = tail[of[-1].end():] if of else ""
        part = re.sub(r"^(?:[\s,;:\d]+|and\s+|the\s+|of\s+|(?:act\s*)?no\.?\s*\d+\s*(?:of\s*)?)+", "", part, flags=re.I)
        if 6 <= len(part) <= 140 and re.search(r"[A-Za-z]{3}", part[:-3]):
            out.append((part, partial))
            carry = False
        else:
            carry = partial
    return out


def candidate_names(text: str) -> list[str]:
    return [n for n, _ in candidate_parts(text)]


async def fetch_edge_chunks(docs: list[dict]) -> tuple[dict[str, str], list[str], list[str]]:
    """The chunks of each document that can hold a repeal or a start date, as one string.

    Also returns the documents whose fetch failed (the build must stop: a
    missing clause would quietly turn a repealed Act back into law) and the
    ones whose repeal-clause query hit its limit (raise REPEAL_HITS if any).
    Every query is ordered, so two runs read the same text.
    """
    base = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/legal_chunks"
    key = os.environ["SUPABASE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    sem = asyncio.Semaphore(8)
    out: dict[str, str] = {}

    async def one(client: httpx.AsyncClient, d: dict):
        queries = [
            {"select": "content", "document_id": f"eq.{d['id']}",
             "chunk_index": f"lt.{HEAD_CHUNKS}", "order": "chunk_index"},
            # The repeal section itself first. A plain "*repeal*" match with a
            # limit returned the definitions ("the repealed Act" means ...)
            # once the Companies Act, 2017 was re-parsed, and s. 376 fell
            # outside the limit (17 Sep 2026).
            {"select": "content", "document_id": f"eq.{d['id']}",
             "or": "(content.ilike.*is repealed*,content.ilike.*are repealed*,content.ilike.*isrepealed*,"
                   "content.ilike.*arerepealed*,content.ilike.*hereby repealed*,"
                   # the long title: "An Act to ... repeal and replace the X Act"
                   "content.ilike.*repeal and replace*,content.ilike.*repealandreplace*,"
                   "content.ilike.*repeals and replaces*)",
             "order": "chunk_index.desc", "limit": str(REPEAL_HITS)},
            {"select": "content", "document_id": f"eq.{d['id']}",
             "content": "ilike.*repeal*", "order": "chunk_index.desc", "limit": str(REPEAL_HITS)},
            # Section 1 is not always in the first chunks (an arrangement of
            # sections can come first), and it says when the Act starts.
            {"select": "content", "document_id": f"eq.{d['id']}",
             "or": "(content.ilike.*into operation*,content.ilike.*into force*)",
             "order": "chunk_index", "limit": "5"},
        ]
        parts: list[str] = []
        async with sem:
            for n, params in enumerate(queries):
                for attempt in range(4):
                    try:
                        r = await client.get(base, params=params, headers=headers, timeout=90)
                        if r.status_code == 200:
                            rows = r.json()
                            parts += [c["content"] for c in rows]
                            if n == 1 and len(rows) >= REPEAL_HITS:
                                saturated.append(d["id"])
                            break
                    except Exception:  # noqa: BLE001
                        pass
                    await asyncio.sleep(1 + 2 * attempt)
                else:
                    failed.append(d["id"])
        out[d["id"]] = "\n".join(parts)

    failed: list[str] = []
    saturated: list[str] = []
    async with httpx.AsyncClient() as client:
        await asyncio.gather(*(one(client, d) for d in docs))
    return out, failed, saturated


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write the map file")
    ap.add_argument("--accept-losses", action="store_true",
                    help="write even if an Act leaves repealed/pending or a bill leaves enacted")
    args = ap.parse_args()

    db = get_db()
    docs, start = [], 0
    while True:
        rows = (db.table("legal_documents")
                .select("id,title,short_name,document_type,year,act_number,total_chunks,is_global")
                .order("id")   # pages without an order can skip or repeat rows
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
        keys = {norm(d["title"]), norm(d.get("short_name") or "")}
        # The parser cut "Act" off some titles ("The Immigration and
        # Deportation 2010", "The Metrology"); index them under the full name.
        keys |= {k + " act" for k in keys if d["document_type"] == "act" and not re.search(r"\b(act|code)\b", k)}
        for key in keys:
            if len(key) > 4 and d["id"] not in index[key]:
                index[key].append(d["id"])

    def doc_year(d: dict) -> int | None:
        # Not from a "[repealed by the Road Traffic Act, 2002]" annotation.
        return (d.get("year") or year_of(d.get("act_number") or "")
                or year_of(re.sub(r"\[[^\]]*\]", " ", d["title"])))

    def resolve(name: str, by: dict | None = None, before: int | None = None) -> list[str]:
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
                    # Leave the repealing Act out before ranking: "The Victoria
                    # Memorial Institute (Repeal) Act" ties with its target and,
                    # once dropped as a self-match, took the target with it.
                    ids = [i for i in ids if not by or i != by["id"]]
                    ot = {w for w in k.split() if w not in STOP}
                    if ids and ot and len(kt & ot) / len(kt | ot) >= 0.75:
                        scored.append((len(kt & ot) / len(kt | ot), k, ids))
                if scored:
                    # best score; a tie goes to the same name on every run
                    hits = list(min(scored, key=lambda x: (-x[0], x[1]))[2])
        if by:
            by_y = doc_year(by)
            hits = [h for h in hits if h != by["id"]
                    and not (by_y and doc_year(by_id[h]) and doc_year(by_id[h]) >= by_y)
                    # An undated repealer is a consolidated Chapter of the 1995
                    # revised edition: it can only repeal what came before that.
                    # Once its text read cleanly, the 1994 Companies Act's
                    # "The Companies Act ... is repealed" (meaning the 1921 Act)
                    # matched the Companies Act, 2017 and marked it dead.
                    and not (not by_y and (doc_year(by_id[h]) or 0) > UNDATED_EDITION_YEAR)]
        want = year_of(name)
        undated = [h for h in hits if not doc_year(by_id[h])]
        if want:
            # "The Food Reserve Act, 2020 is repealed" is not the 1989 Act.
            # Undated rows stay: they are Chapter editions or copies whose
            # year the parser missed ("The Rating Act" beside "The Rating",
            # 1997), and may be the Act named.
            exact = [h for h in hits if doc_year(by_id[h]) == want]
            if exact:
                return exact + undated
            # Without the named version, only older ones are surely dead.
            return [h for h in hits if (doc_year(by_id[h]) or 0) < want]
        dated = [doc_year(by_id[h]) for h in hits if doc_year(by_id[h])]
        if before:
            # "Companies (Amendment) Act, 2011" amends the Act of that name in
            # force in 2011, not the Companies Act, 2017.
            dated = [y for y in dated if y <= before]
            if not dated:
                return undated
        if len(hits) > 1 and dated:
            # An undated name in a new Act means the version in force when it
            # passed: the Immigration Control Act, 2026 repeals the 2010
            # Immigration and Deportation Act, not the 1965 one before it.
            newest = max(dated)
            hits = [h for h in hits if doc_year(by_id[h]) in (None, newest)]
        return hits

    scan = [d for d in docs if d["document_type"] in ("act", "court_rule")]
    print(f"documents {len(docs)} | scanning {len(scan)} acts and rules for repeal clauses", flush=True)
    text, failed, saturated = asyncio.run(fetch_edge_chunks(scan))
    print(f"fetched edge text for {len(text)} documents", flush=True)
    if failed:
        # A document read without its repeal clause turns a repealed Act back
        # into law. Better no new map than a quietly wrong one.
        print(f"FETCH FAILED for {len(failed)} documents, nothing written: "
              + ", ".join(by_id[i]["title"][:40] for i in failed[:5]), flush=True)
        return 1
    if saturated:
        print(f"note: {len(saturated)} documents have at least {REPEAL_HITS} repeal-clause chunks; "
              f"raise REPEAL_HITS if a repeal goes missing: "
              + ", ".join(by_id[i]["title"][:40] for i in saturated[:5]), flush=True)

    repeals: list[dict] = []          # {by, target_id|None, name, evidence}
    amends: list[dict] = []
    unresolved: list[dict] = []

    deferred: dict[str, bool] = {}
    for d in scan:
        body = clean_clause(text.get(d["id"], ""))
        deferred[d["id"]] = bool(RE_DEFERRED.search(re.sub(r"\s+", "", body)))
        found: list[tuple[str, str]] = []
        for m in RE_REPEALED.finditer(body):
            for nm, partial in candidate_parts(m.group("list")):
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
            # "Roads and Road Traffic Act [repealed by the Road Traffic Act,
            # 2002 and ...]" fuzzy-matches its own title, and an Act never
            # repeals itself. With the repealer absent from the library the
            # note keeps the annotation's own wording.
            for tid in [t for t in resolve(m.group("name")) if t != d["id"]] or [None]:
                repeals.append({"by": tid, "target": d["id"], "name": m.group("name").strip(),
                                "evidence": "title annotation"})
        m = RE_REPEAL_ACT_TITLE.match(re.sub(r"\[[^\]]*\]", "", d["title"]))
        if m and "amendment" not in d["title"].lower():
            for tid in resolve(m.group("stem") + " Act", by=d):
                repeals.append({"by": d["id"], "target": tid, "name": m.group("stem").strip(),
                                "evidence": "(Repeal) Act title"})
        m = RE_AMENDMENT_TITLE.match(d["title"])
        if m:
            for pid in resolve(m.group("stem") + " Act", by=None, before=doc_year(d)):
                if "(amendment)" in by_id[pid]["title"].lower():
                    continue    # an amendment does not amend another amendment
                amends.append({"by": d["id"], "target": pid})

    # ---- assemble ----
    entry: dict[str, dict] = {}

    def slot(doc_id: str) -> dict:
        return entry.setdefault(doc_id, {"status": "in force", "repealed_by": [], "repeals": [],
                                         "partially_repealed_by": [], "amended_by": [], "amends": [],
                                         "enacted_as": [], "repeal_pending_by": []})

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
        if by and deferred.get(by["id"]) and (doc_year(by) or 0) >= PENDING_FROM_YEAR:
            add(t["repeal_pending_by"], note)
            if t["status"] != "repealed":
                t["status"] = "repeal pending"
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
    act_names: dict[str, list[dict]] = defaultdict(list)
    for d in docs:
        if d["document_type"] == "act":
            act_names[norm(d["title"])].append(d)
    for d in docs:
        if d["document_type"] != "bill":
            continue
        # Same name is not enough: "The Land (Perpetual Succession) Bill" would
        # match the old Act of that name. The Act must carry the bill's year,
        # and every Act of that name is checked: norm() drops the year, so the
        # 2010 and 2026 amendment Acts share a key, and keeping only one of
        # them flipped bills between "enacted" and "not yet law" from run to run.
        bill_year = year_of(d["title"])
        same = act_names.get(norm(re.sub(r"\bbill\b", "Act", d["title"], flags=re.I)), [])
        as_act = next((a for a in same if bill_year and bill_year in (year_of(a["title"]), a.get("year"))), None)
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

    # An Act that stops reading as repealed goes back to being law in every
    # answer. On 17 Sep a change to which chunks were fetched did exactly that
    # to the 1994 Companies Act, and only a manual diff caught it.
    losses = []
    if OUT.exists():
        previous = json.loads(OUT.read_text()).get("documents", {})
        for doc_id, old in previous.items():
            new_status = (entry.get(doc_id) or {}).get("status")
            if old.get("status") in ("repealed", "repeal pending") and new_status not in ("repealed", "repeal pending"):
                losses.append((old.get("title") or doc_id, old["status"], new_status))
            elif old.get("status") == "enacted" and new_status != "enacted":
                losses.append((old.get("title") or doc_id, old["status"], new_status))
    if losses:
        print(f"\nSTATUS LOSSES against the current map: {len(losses)}")
        for title, was, now in losses[:20]:
            print(f"  {title[:60]:62} {was} -> {now}")

    if args.write and losses and not args.accept_losses:
        print("\nnothing written: check these, then rerun with --accept-losses if they are right")
        return 1
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        # Each entry names its own document, so the prompt can list repealed
        # Acts and the citation audit can say which Act it flagged without a
        # database round trip.
        for doc_id, e in entry.items():
            d = by_id.get(doc_id) or {}
            e["title"] = d.get("title") or ""
            e["short_name"] = d.get("short_name") or ""
            e["year"] = doc_year(d) if d else None
            e["is_global"] = bool(d.get("is_global"))
        payload = json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "documents": entry,
            "unresolved": unresolved[:200],
        }, indent=1)
        # A failed or interrupted write must never leave production with a
        # truncated map.  Build beside the destination, then replace it in one
        # filesystem operation; this does not alter any map-building logic.
        fd, temporary = tempfile.mkstemp(prefix=f".{OUT.name}.", dir=OUT.parent)
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(payload)
            os.chmod(temporary, OUT.stat().st_mode if OUT.exists() else 0o644)
            os.replace(temporary, OUT)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        print(f"\nwrote {OUT} ({OUT.stat().st_size // 1024} KB, {len(entry)} documents)")
    else:
        print("\n(report only; pass --write to save the map)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
