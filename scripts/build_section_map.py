#!/usr/bin/env python3
"""Which sections of which Acts have been repealed, replaced, amended or inserted.

The law map (build_law_map.py) knows whole Acts. This reads inside every
amending Act it links to a principal, and records what each one did to each
section, so a search hit on section 24 of the Immigration and Deportation Act
2010 can say it was repealed by Act No. 19 of 2016 before the model quotes it.

Found by the first head-to-head benchmark on 28 September 2026: ChatGPT with
web search caught that repeal, and Levy, which holds the amending Act, did not.
At the time the corpus held 273 amending Acts; the law map linked them to
their principals and nothing read what they did.

    python scripts/build_section_map.py            # report
    python scripts/build_section_map.py --write    # write backend/app/data/section_map.json

Run it after build_law_map.py, because it reads that map's links.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import types
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))
from app.db.supabase import get_db  # noqa: E402
from app.services.section_ops import extract_ops  # noqa: E402

LAW_MAP = REPO / "backend" / "app" / "data" / "law_map.json"
OUT = REPO / "backend" / "app" / "data" / "section_map.json"
# Same convention as build_law_map.py: an undated principal is a consolidated
# Chapter of the revised edition, which already contains amendments made up
# to about then.
UNDATED_EDITION_YEAR = 1996
RANK = {"high": 2, "medium": 1}


def chunks_of(db, doc_id: str) -> list[str]:
    out, start = [], 0
    while True:
        rows = (db.table("legal_chunks").select("content,chunk_index")
                .eq("document_id", doc_id).order("chunk_index")
                .range(start, start + 199).execute().data)
        out += [r["content"] or "" for r in rows]
        if len(rows) < 200:
            return out
        start += 200


def ops_of_act(texts: list[str]) -> list[dict]:
    """Every op one amending Act performs, merged across its chunks."""
    best: dict[tuple[str, str, str], dict] = {}
    for text in texts:
        for o in extract_ops(text):
            key = (o["op"], o["kind"], o["target"])
            if key not in best or RANK[o["confidence"]] > RANK[best[key]["confidence"]]:
                best[key] = o
    ops = list(best.values())
    # A clause cut by a chunk boundary reads "repeal of section 56" in one
    # chunk and "... and the substitution therefor" in the next. The section
    # still exists, so the replacement wins.
    replaced = {(o["kind"], o["target"]) for o in ops if o["op"] == "replaced"}
    ops = [o for o in ops if not (o["op"] == "repealed" and (o["kind"], o["target"]) in replaced)]
    return sorted(ops, key=lambda o: (o["kind"], o["target"].zfill(6), o["op"]))


def principals(lm: dict, amending: dict, year: int | None) -> tuple[list[str], list[str]]:
    """The principal Acts this amendment really applies to, and why others were dropped."""
    keep, dropped = [], []
    for ref in amending.get("amends") or []:
        pid = ref.get("id")
        p = lm.get(pid) or {}
        if not pid:
            continue
        py = p.get("year")
        if year and py and py > year:
            dropped.append(f"{p.get('title', pid)[:50]}: principal is newer than the amendment")
            continue
        if p.get("status") == "repealed" and year:
            # The Immigration and Deportation (Amendment) Act 2016 is linked
            # to the 1965 Act as well as the 2010 one. The 1965 Act was dead
            # by 2016; its section 24 is not the section 24 that was repealed.
            gone = [(lm.get(r.get("id") or "") or {}).get("year") for r in p.get("repealed_by") or []]
            if any(g and g <= year for g in gone):
                dropped.append(f"{p.get('title', pid)[:50]}: already repealed by then")
                continue
        if not py and year and year <= UNDATED_EDITION_YEAR:
            dropped.append(f"{p.get('title', pid)[:50]}: undated edition likely already contains it")
            continue
        keep.append(pid)
    return keep, dropped


def current_state(history: list[dict]) -> str:
    """What the section is now, after every recorded op in date order."""
    state = "original"
    for h in history:
        op = h["op"]
        if op != "amended":
            state = op          # repealed, replaced or inserted
            continue
        if state == "repealed":
            # Amending a section recorded as repealed means one of the two
            # readings is wrong, or a re-insertion was not recognised. Say so
            # rather than pick one.
            return "uncertain"
        if state in ("replaced", "inserted"):
            continue            # new wording, since amended again: still not the original
        state = "amended"
    return state


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--accept-losses", action="store_true",
                    help="write even if a section stops reading as repealed")
    args = ap.parse_args()

    lm = json.loads(LAW_MAP.read_text())["documents"]
    db = get_db()
    amending_ids = sorted(d for d, e in lm.items() if e.get("status") == "amending Act")
    numbers: dict[str, str] = {}
    for i in range(0, len(amending_ids), 150):
        rows = (db.table("legal_documents").select("id,act_number,document_type")
                .in_("id", amending_ids[i:i + 150]).execute().data)
        for r in rows:
            if r.get("document_type") == "act":
                numbers[r["id"]] = r.get("act_number") or ""
    # Bills are proposals: what a Bill would do to a section is not law.
    amending_ids = [d for d in amending_ids if d in numbers]
    print(f"amending Acts: {len(amending_ids)}", flush=True)

    principals_out: dict[str, dict] = {}
    no_ops, dropped_links = [], []
    for n, did in enumerate(amending_ids, 1):
        a = lm[did]
        year = a.get("year")
        ops = ops_of_act(chunks_of(db, did))
        if not ops:
            no_ops.append(a.get("title") or did)
            continue
        keep, dropped = principals(lm, a, year)
        dropped_links += [f"{(a.get('title') or '')[:44]} -/-> {d}" for d in dropped]
        for pid in keep:
            p = principals_out.setdefault(pid, {"title": (lm.get(pid) or {}).get("title", ""),
                                                "sections": {}, "parts": {}})
            for o in ops:
                bucket = p["sections"] if o["kind"] == "section" else p["parts"]
                bucket.setdefault(o["target"], {"history": []})["history"].append({
                    "op": o["op"],
                    "by_id": did,
                    "by_title": a.get("title") or "",
                    "by_number": numbers.get(did, ""),
                    "by_year": year,
                    "confidence": o["confidence"],
                    "evidence": o["evidence"],
                })
        if n % 40 == 0:
            print(f"  ...{n}/{len(amending_ids)}", flush=True)

    counts: Counter = Counter()
    for p in principals_out.values():
        for bucket in (p["sections"], p["parts"]):
            for ref, s in bucket.items():
                s["history"].sort(key=lambda h: (h["by_year"] or 0, h["by_title"]))
                s["current"] = current_state(s["history"])
                counts[s["current"]] += 1

    print(f"\nprincipal Acts with section-level changes: {len(principals_out)}")
    print(f"sections/parts by current state: {dict(counts)}")
    print(f"amending Acts with no readable section ops: {len(no_ops)}")
    for t in no_ops[:12]:
        print(f"    {t[:70]}")
    print(f"links dropped: {len(dropped_links)}")
    for d in dropped_links[:12]:
        print(f"    {d}")
    print("\nREPEALED (current):")
    for pid, p in sorted(principals_out.items(), key=lambda kv: kv[1]["title"]):
        for ref, s in sorted(p["sections"].items(), key=lambda kv: kv[0].zfill(6)):
            if s["current"] == "repealed":
                h = s["history"][-1]
                print(f"  {p['title'][:44]:<44} s.{ref:<6} by {h['by_title'][:40]} ({h['confidence']})")
    uncertain = [(p["title"], ref) for p in principals_out.values()
                 for ref, s in p["sections"].items() if s["current"] == "uncertain"]
    if uncertain:
        print(f"\nUNCERTAIN (repealed, then amended): {len(uncertain)}")
        for t, ref in uncertain[:10]:
            print(f"  {t[:50]} s.{ref}")

    # A section that stops reading as repealed goes back to being quoted as
    # law. Same guard as the law map.
    losses = []
    if OUT.exists():
        prev = json.loads(OUT.read_text()).get("principals", {})
        for pid, p in prev.items():
            if pid not in lm:
                continue    # the principal itself left the library: nothing to protect
            for ref, s in p.get("sections", {}).items():
                now = (((principals_out.get(pid) or {}).get("sections") or {}).get(ref) or {}).get("current")
                if s.get("current") == "repealed" and now != "repealed":
                    losses.append((p.get("title", pid), ref, now))
    if losses:
        print(f"\nSTATUS LOSSES against the current map: {len(losses)}")
        for t, ref, now in losses[:20]:
            print(f"  {t[:50]} s.{ref}: repealed -> {now}")
        if args.write and not args.accept_losses:
            print("nothing written: check these, then rerun with --accept-losses if they are right")
            return 1

    if not args.write:
        print("\n(report only; pass --write to save)")
        return 0
    payload = json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "principals": principals_out,
        "amending_acts_without_ops": sorted(no_ops),
    }, indent=1, sort_keys=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{OUT.name}.", dir=OUT.parent)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(payload)
        os.chmod(tmp, 0o644)
        os.replace(tmp, OUT)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    print(f"\nwrote {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
