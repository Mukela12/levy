#!/usr/bin/env python3
"""Put the benchmark to a rival model, and file its reply for grading.

Levy is asked through its own API, which is scriptable. ChatGPT and Claude are
asked the way a person would ask them, which is the honest comparison anyway:
the same nine questions, cold, in one message.

  python bench/capture.py --prompt                       # copy this into the chat
  python bench/capture.py --model chatgpt --from reply.txt

The reply is split on the `### <question-id>` headings the prompt asks for. If
a model ignores the format, `--manual` takes one answer at a time instead.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUESTIONS = json.loads((ROOT / "questions.json").read_text())

PREAMBLE = """You are being asked nine questions about Zambian law for a benchmark.

Answer each one as fully and accurately as you can. Where the law has a
specific source, name it: the Act, its number and year, and the section.
If you do not know or cannot verify something, say so plainly rather than
guessing.

Put each answer under a heading exactly matching its id, like this:

### meal-break
<your answer>

### notice-period
<your answer>

Here are the questions:
"""


def prompt_text() -> str:
    lines = [PREAMBLE]
    for q in QUESTIONS:
        lines.append(f"\n### {q['id']}\n{q['question']}")
    return "\n".join(lines)


def split_reply(text: str) -> dict[str, str]:
    ids = [q["id"] for q in QUESTIONS]
    # Accept "### id", "**id**", "id:" — models reformat headings constantly.
    pattern = re.compile(
        r"^[ \t]*(?:#{1,6}[ \t]*|\*\*)?(" + "|".join(re.escape(i) for i in ids) + r")(?:\*\*)?[ \t]*:?[ \t]*$",
        re.I | re.M,
    )
    marks = [(m.start(), m.end(), m.group(1).lower()) for m in pattern.finditer(text)]
    out: dict[str, str] = {}
    for i, (_, end, qid) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out[qid] = text[end:stop].strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", action="store_true", help="print the block to paste into the rival chat")
    ap.add_argument("--model", help="name to file the answers under, e.g. chatgpt or claude")
    ap.add_argument("--from", dest="src", type=Path, help="file holding the model's whole reply")
    ap.add_argument("--manual", action="store_true", help="paste answers one question at a time")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()

    if args.prompt:
        print(prompt_text())
        return 0
    if not args.model:
        ap.error("--model is required unless --prompt")

    if args.manual:
        answers = []
        for q in QUESTIONS:
            print(f"\n=== {q['id']}\n{q['question']}\n\nPaste the answer, then a line with only END:")
            buf = []
            for line in sys.stdin:
                if line.strip() == "END":
                    break
                buf.append(line)
            answers.append({"id": q["id"], "answer": "".join(buf).strip()})
    else:
        if not args.src:
            ap.error("--from FILE is required unless --manual")
        found = split_reply(args.src.read_text())
        missing = [q["id"] for q in QUESTIONS if q["id"] not in found]
        if missing:
            print(f"warning: no heading found for {', '.join(missing)} "
                  f"— they will score zero. Re-run with --manual if that is wrong.", file=sys.stderr)
        answers = [{"id": q["id"], "answer": found.get(q["id"], "")} for q in QUESTIONS]

    out = ROOT / "results" / f"{args.date}-{args.model}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"model": args.model, "date": args.date, "answers": answers}, indent=1))
    filled = sum(1 for a in answers if a["answer"])
    print(f"wrote {out}  ({filled}/{len(answers)} answered)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
