#!/usr/bin/env python3
"""Score one model's answers against the benchmark's verified ground truth.

The point of this benchmark is not whether an answer reads well. A general
model writes beautifully about Zambian law and gets the section number wrong,
which is the failure that matters to someone filing a document. So the scoring
is deliberately mechanical and checks three things:

  grounded   did it name the right instrument and provision?
  correct    did it state the operative fact?
  honest     did it avoid the traps: a repealed Act applied as current, a
             Bill described as law, facts invented for a case that does not
             exist?

Every rule is a list of alternative regexes; any one of them satisfies it.
Ground truth was read out of Levy's own corpus and law map, not from memory,
and each question records where it was verified.

  python bench/grade.py bench/results/2026-09-28-levy.json
  python bench/grade.py bench/results/2026-09-28-*.json     # compare models
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUESTIONS = {q["id"]: q for q in json.loads((ROOT / "questions.json").read_text())}


def _hit(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.I | re.S) for p in patterns)


def score_answer(question: dict, answer: str) -> dict:
    text = " ".join((answer or "").split())
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

    # A trap is not worth a point for avoiding it; it is a penalty for falling
    # in. Inventing the facts of a case that does not exist is not "one mark
    # short", it is the whole reason a lawyer cannot trust the tool.
    tripped = [rule[0] for rule in question.get("must_not", []) if _hit(rule, text)]

    return {
        "id": question["id"],
        "category": question["category"],
        "earned": earned,
        "available": available,
        "score": (earned / available) if available else None,
        "tripped": tripped,
        "misses": misses,
        "empty": not text,
    }


def score_run(run: dict) -> dict:
    rows = [score_answer(QUESTIONS[a["id"]], a.get("answer", ""))
            for a in run["answers"] if a["id"] in QUESTIONS]
    earned = sum(r["earned"] for r in rows)
    available = sum(r["available"] for r in rows)
    return {
        "model": run.get("model", "?"),
        "date": run.get("date", "?"),
        "rows": rows,
        "earned": earned,
        "available": available,
        "percent": (100 * earned / available) if available else 0.0,
        "traps_tripped": sum(1 for r in rows if r["tripped"]),
        "unanswered": sum(1 for r in rows if r["empty"]),
    }


def main(paths: list[str]) -> int:
    runs = [score_run(json.loads(Path(p).read_text())) for p in paths]
    if not runs:
        print("usage: python bench/grade.py bench/results/<date>-<model>.json ...")
        return 2

    width = max(len(r["model"]) for r in runs) + 2
    print(f"\n{'model':<{width}} {'grounded+correct':>17} {'traps tripped':>14} {'blank':>6}")
    print("-" * (width + 40))
    for r in sorted(runs, key=lambda x: -x["percent"]):
        print(f"{r['model']:<{width}} {r['earned']:>6}/{r['available']:<3} {r['percent']:>5.0f}%"
              f" {r['traps_tripped']:>13} {r['unanswered']:>6}")

    print("\nby question:")
    ids = [q for q in QUESTIONS]
    head = f"  {'question':<20} {'category':<19}" + "".join(f"{r['model'][:11]:>12}" for r in runs)
    print(head)
    print("  " + "-" * (len(head) - 2))
    for qid in ids:
        q = QUESTIONS[qid]
        line = f"  {qid:<20} {q['category']:<19}"
        for r in runs:
            row = next((x for x in r["rows"] if x["id"] == qid), None)
            if row is None:
                line += f"{'-':>12}"
            elif row["tripped"]:
                line += f"{'TRAP':>12}"
            elif row["score"] is None:
                line += f"{'n/a':>12}"
            else:
                line += f"{row['earned']}/{row['available']:<2}".rjust(12)
        print(line)

    for r in runs:
        detail = [x for x in r["rows"] if x["misses"] or x["tripped"]]
        if not detail:
            continue
        print(f"\n{r['model']} — where it went wrong:")
        for x in detail:
            for t in x["tripped"]:
                print(f"    {x['id']}: TRIPPED A TRAP ({t})")
            for m in x["misses"]:
                print(f"    {x['id']}: {m}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
