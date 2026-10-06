#!/usr/bin/env python3
"""Score answers against the benchmark's verified ground truth.

The point of this benchmark is not whether an answer reads well. A general
model writes beautifully about Zambian law and gets the section wrong, or
quotes a repealed one, which is the failure that matters to someone filing a
document on Monday. So the scoring is mechanical:

  grounded   the right instrument AND the right provision (section scoring:
             "Employment Code" and "section 77" near each other, not anywhere)
  correct    the operative fact is stated
  current    dead law (a repealed Act or section, an Act passed but not in
             force, a Bill) may be MENTIONED, but every mention must say it is
             dead. Applying it as current law is the failure that started this
             benchmark: section 24 of the Immigration and Deportation Act 2010,
             repealed in 2016. Judged per block (the text under one heading);
             --audit adds Levy's stricter per-sentence citation audit.
  premise    a false-premise question must have its premise rejected; models
             tend to accept a user's wrong legal assumption and answer on it
  traps      inventing facts for a case that does not exist, and other
             question-specific failures (must_not)

Each answer then gets one grade on the rubric of Magesh et al. (Stanford,
2024/2025), so results are comparable with the published legal-RAG studies:
  hallucinated  a trap tripped, dead law applied, or a false premise accepted
  correct       none of those, and everything required is there
  incomplete    the rest, including a refusal where an answer was expected

A grader this mechanical decides nothing on ten questions: the 95% interval
is printed beside each rate to say so. Claims need the frozen gold set.

  python bench/grade.py bench/results/2026-10-06-*.json
  python bench/grade.py --audit RUN.json           # + Levy's citation audit (database reads, free)
  python bench/grade.py --export-judge out.jsonl RUN.json   # for human or model grading later
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUESTIONS = {q["id"]: q for q in json.loads((ROOT / "questions.json").read_text())}

# Saying law is dead, in any of the ways answers say it. Judged per block
# (the text under one heading): an answer that describes a repealed section in
# the past tense and says "critically, section 24 has been repealed" in the
# next paragraph has told the reader. Levy's stricter per-sentence audit is
# the separate --audit measure.
_DEAD_ACK = re.compile(
    r"repeal|no longer|replaced|superseded|abolish|used to|formerly|historical|while it existed|"
    r"not (?:yet )?(?:in force|commenced|operational)|not (?:been )?shown to be in force|"
    r"has not (?:yet )?(?:commenced|come into)|no commencement order|awaiting (?:a |its )?commencement|"
    r"until it commences|passed but|not (?:yet )?(?:been )?enacted|still a bill|before parliament|"
    r"no (?:legal )?force|not (?:yet )?law", re.I)
# Top-level sections only: a "### Section 73" under "## What the old Act
# said (historical)" belongs to its parent.
_BLOCKS = re.compile(r"\n(?=#{1,2}\s)|\n\s*(?:-{3,}|\*{3,})\s*\n")


def _blocks(text: str) -> list[str]:
    """Answer sections, with a heading-only block joined to the text under it."""
    out: list[str] = []
    carry = ""
    for b in _BLOCKS.split(text):
        lines = [x for x in b.strip().splitlines() if x.strip()]
        if len(lines) <= 1 and lines and lines[0].lstrip().startswith("#"):
            carry += b + "\n"
            continue
        out.append(carry + b)
        carry = ""
    if carry:
        out.append(carry)
    return out
WINDOW = 220  # characters between an instrument's name and its provision


def _hit(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.I | re.S) for p in patterns)


def provision_cited(text: str, authority: list[str], provision: list[str]) -> bool:
    """The instrument and the provision within WINDOW characters of each other,
    so a stray "section 77" elsewhere in the answer does not count."""
    for a in authority:
        for m in re.finditer(a, text, re.I):
            lo, hi = max(0, m.start() - WINDOW), m.end() + WINDOW
            if _hit(provision, text[lo:hi]):
                return True
    return False


def dead_law_findings(text: str, items: list[dict]) -> list[dict]:
    """Each dead instrument the answer mentions, and whether every block that
    mentions it also says it is dead."""
    out = []
    blocks = _blocks(text)
    for item in items:
        rx = re.compile("|".join(f"(?:{p})" for p in item["mention"]), re.I)
        mentioned = [b for b in blocks if rx.search(b)]
        if not mentioned:
            continue
        bare = [" ".join(b.split())[:160] for b in mentioned if not _DEAD_ACK.search(b)]
        out.append({"label": item["label"], "kind": item.get("kind", "repealed"),
                    "acknowledged": not bare, "unacknowledged_in": bare})
    return out


def score_answer(question: dict, answer: str) -> dict:
    raw = answer or ""
    text = " ".join(raw.split())
    earned = available = 0
    misses: list[str] = []

    for rule in question.get("must_cite", []):
        available += 1
        if _hit(rule, text):
            earned += 1
        else:
            misses.append(f"did not cite: {rule[0]}")
    for rule in question.get("must_state", []):
        available += 1
        if _hit(rule, text):
            earned += 1
        else:
            misses.append(f"did not state: {rule[0]}")
    sections_hit = sections_total = 0
    for p in question.get("provisions", []):
        available += 1
        sections_total += 1
        if provision_cited(text, p["authority"], p["provision"]):
            earned += 1
            sections_hit += 1
        else:
            misses.append(f"did not cite the provision: {p['label']}")

    # A trap is not worth a point for avoiding it; it is a penalty for falling in.
    tripped = [rule[0] for rule in question.get("must_not", []) if _hit(rule, text)]
    # The acknowledgement logic reads sentence ends and headings, so it gets
    # the answer with its line breaks.
    dead = dead_law_findings(raw, question.get("dead_law", []))
    applied_dead = [d["label"] for d in dead if not d["acknowledged"]]
    premise = question.get("false_premise")
    premise_rejected = None if not premise else _hit(premise["reject"], text)

    # A refusal is read from the opening, so "I could not find the penalty
    # provision" deep in a full answer does not turn it into one.
    refused = not text or bool(re.search(r"\b(cannot|can't|could not|couldn't|unable to) (find|locate|give you)",
                                         text[:300], re.I))
    if tripped or applied_dead or premise_rejected is False:
        grade = "hallucinated"
    elif available and earned == available and not (refused and not question.get("refusal_expected")):
        grade = "correct"
    elif not available and not (refused and not question.get("refusal_expected")):
        grade = "correct"
    else:
        grade = "incomplete"

    return {
        "id": question["id"], "category": question["category"],
        "earned": earned, "available": available, "score": (earned / available) if available else None,
        "sections_hit": sections_hit, "sections_total": sections_total,
        "tripped": tripped, "dead_law": dead, "applied_dead": applied_dead,
        "premise_rejected": premise_rejected, "misses": misses, "empty": not text, "grade": grade,
    }


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% interval for a proportion. On ten questions it spans most of the scale."""
    if not n:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def score_run(run: dict, audit: bool = False) -> dict:
    answers = [a for a in run["answers"] if a["id"] in QUESTIONS]
    rows = [score_answer(QUESTIONS[a["id"]], a.get("answer", "")) for a in answers]
    out = {"model": run.get("model", "?"), "date": run.get("date", "?"), "rows": rows,
           "earned": sum(r["earned"] for r in rows), "available": sum(r["available"] for r in rows),
           "grades": {g: sum(1 for r in rows if r["grade"] == g) for g in ("correct", "incomplete", "hallucinated")},
           "n": len(rows), "unanswered": sum(1 for r in rows if r["empty"])}
    out["percent"] = 100 * out["earned"] / out["available"] if out["available"] else 0.0
    if audit:
        sys.path.insert(0, str(ROOT.parent / "backend"))
        sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))
        from app.services.citation_audit import audit_answer
        nf = dead = total = 0
        for a in answers:
            for c in audit_answer(a.get("answer", "")):
                total += 1
                if c.get("status") == "not_found" and not c.get("foreign"):
                    nf += 1
                if (c.get("law_status") in ("repealed", "not in force") and not c.get("acknowledged")) or any(
                        not d.get("acknowledged") for d in c.get("section_status") or []):
                    dead += 1
        out["audit"] = {"citations": total, "not_in_library": nf, "dead_law_unacknowledged": dead}
    return out


def export_judge(path: str, runs_raw: list[dict]) -> None:
    """One line per answer, for grading against the ground truth by a person or
    a model later. Nothing is sent anywhere here."""
    rubric = ("Grade the ANSWER against the GROUND TRUTH, element by element. Return one of: correct (every "
              "element right and supported), incomplete (nothing false, but an element missing, or a refusal "
              "where an answer existed), hallucinated (any false statement of law or fact, a real authority "
              "cited for a proposition it does not support, or dead law applied as current). Then list each "
              "citation in the answer as grounded or misgrounded.")
    with open(path, "w") as fh:
        for run in runs_raw:
            for a in run["answers"]:
                q = QUESTIONS.get(a["id"])
                if not q:
                    continue
                fh.write(json.dumps({"model": run.get("model"), "id": a["id"], "question": q["question"],
                                     "ground_truth": q["ground_truth"], "verified_against": q.get("verified_against"),
                                     "answer": a.get("answer", ""), "rubric": rubric}) + "\n")
    print(f"wrote {path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--audit", action="store_true", help="also run Levy's citation audit on every answer")
    ap.add_argument("--export-judge", help="write question / ground truth / answer lines for later grading")
    args = ap.parse_args()
    raw = [json.loads(Path(p).read_text()) for p in args.paths]
    if not raw:
        print(__doc__)
        return 2
    if args.export_judge:
        export_judge(args.export_judge, raw)
    runs = [score_run(r, args.audit) for r in raw]

    width = max(len(r["model"]) for r in runs) + 2
    print(f"\n{'model':<{width}} {'n':>3} {'correct':>16} {'incomplete':>11} {'hallucinated':>13} {'points':>10}")
    print("-" * (width + 60))
    for r in sorted(runs, key=lambda x: (-x["grades"]["correct"], x["grades"]["hallucinated"])):
        g, n = r["grades"], r["n"]
        lo, hi = wilson(g["correct"], n)
        print(f"{r['model']:<{width}} {n:>3} {g['correct']:>4} ({lo:.0%}-{hi:.0%}) {g['incomplete']:>11} "
              f"{g['hallucinated']:>13} {r['earned']:>5}/{r['available']:<3}")
        if "audit" in r:
            a = r["audit"]
            print(f"{'':<{width}}     citation audit: {a['citations']} citations, {a['not_in_library']} not in Levy's "
                  f"library, {a['dead_law_unacknowledged']} relying on dead law unacknowledged")
    print("  (interval: 95% Wilson on the correct rate; it is wide on purpose: n is small)")

    print("\nby question:")
    head = f"  {'question':<24} {'category':<20}" + "".join(f"{r['model'][:14]:>16}" for r in runs)
    print(head)
    print("  " + "-" * (len(head) - 2))
    for qid, q in QUESTIONS.items():
        line = f"  {qid:<24} {q['category'][:20]:<20}"
        for r in runs:
            row = next((x for x in r["rows"] if x["id"] == qid), None)
            cell = "-" if row is None else {"correct": "ok", "incomplete": "part", "hallucinated": "HALLUC"}[row["grade"]]
            if row is not None and row["sections_total"]:
                cell += f" s{row['sections_hit']}/{row['sections_total']}"
            line += f"{cell:>16}"
        print(line)

    for r in runs:
        detail = [x for x in r["rows"] if x["misses"] or x["tripped"] or x["applied_dead"] or x["premise_rejected"] is False]
        if not detail:
            continue
        print(f"\n{r['model']}, where it went wrong:")
        for x in detail:
            for t in x["tripped"]:
                print(f"    {x['id']}: TRIPPED A TRAP ({t})")
            for d in x["applied_dead"]:
                print(f"    {x['id']}: DEAD LAW WITHOUT SAYING SO ({d})")
            if x["premise_rejected"] is False:
                print(f"    {x['id']}: ACCEPTED A FALSE PREMISE")
            for m in x["misses"]:
                print(f"    {x['id']}: {m}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
