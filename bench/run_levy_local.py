#!/usr/bin/env python3
"""Run the benchmark through Levy's harness locally, on one chosen model.

run_levy.py measures production. This measures a model the production chain
only reaches when others fail, without waiting for an outage: the same agent
loop, prompt, tools and corpus, with the chain cut down to the model asked
for. Anthropic is never called (unless you name a Claude id), so a run costs
only that model's tokens.

    python bench/run_levy_local.py --model anthropic/claude-sonnet-5.5
    python bench/run_levy_local.py --model openrouter/free --only meal-break

OpenRouter ids need OPENROUTER_API_KEY in the environment. Spend is read off
the OpenRouter account before and after, so the number printed is what was
billed. --max-spend stops the run once it passes that many dollars.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import sys
import time
import types
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))
sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))
from app.config import get_settings  # noqa: E402
from app.services import agent, openrouter  # noqa: E402


def openrouter_spend() -> float | None:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    r = httpx.get("https://openrouter.ai/api/v1/credits",
                  headers={"Authorization": f"Bearer {key}"}, timeout=30)
    return float((r.json().get("data") or {}).get("total_usage") or 0)


async def ask(question: str, model: str) -> dict:
    started = time.time()
    text, tools, models, error = [], [], set(), None
    async for ev in agent.run_agent(user_query=question, model=model, web_enabled=True):
        t = ev.get("type")
        if t == "token":
            text.append(ev.get("content") or "")
        elif t == "tool_call":
            tools.append(ev.get("name"))
        elif t == "error":
            error = ev.get("message")
        elif t == "done":
            models.add(ev.get("model"))
    out = {"answer": "".join(text), "seconds": round(time.time() - started, 1),
           "tool_calls": len(tools), "tools": tools, "answered_by": sorted(m for m in models if m)}
    if error:
        out["error"] = error
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--only", action="append", help="question id; repeatable")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--max-spend", type=float, default=3.0, help="dollars; stop once passed")
    args = ap.parse_args()

    s = get_settings()
    # Cut the chain to the model asked for: no Claude fallbacks, no Kimi, and
    # for an OpenRouter model no hop to the free router either.
    agent.FALLBACK_MODELS = []
    s.moonshot_api_key = ""
    if openrouter.is_openrouter_model(args.model):
        s.openrouter_api_key = os.environ.get("OPENROUTER_API_KEY", "")
        s.openrouter_fallback_model, s.openrouter_free_model = args.model, ""
        if not s.openrouter_api_key:
            print("OPENROUTER_API_KEY is not set")
            return 1
    else:
        s.openrouter_api_key = ""

    questions = json.loads((ROOT / "questions.json").read_text())
    if args.only:
        questions = [q for q in questions if q["id"] in set(args.only)]
    date = dt.date.today().isoformat()
    slug = re.sub(r"[^a-z0-9.]+", "-", args.model.lower()).strip("-")
    out_path = args.out or ROOT / "results" / f"{date}-levy-{slug}.json"

    spent0 = openrouter_spend()
    answers = []
    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q['id']}", flush=True)
        try:
            a = asyncio.run(ask(q["question"], args.model))
        except Exception as e:  # noqa: BLE001 — one bad question must not lose the run
            a = {"answer": "", "error": f"{type(e).__name__}: {e}"[:300]}
        answers.append({"id": q["id"], **a})
        spent = openrouter_spend()
        cost = None if spent0 is None or spent is None else round(spent - spent0, 4)
        print(f"    {len(a['answer'])} chars, {a.get('seconds')}s, {a.get('tool_calls')} tools, "
              f"by {a.get('answered_by')}, spent so far ${cost}" + (f", ERROR {a['error']}" if a.get("error") else ""),
              flush=True)
        out_path.write_text(json.dumps({"model": f"levy-{slug}", "date": date, "api": "local",
                                        "spent_usd": cost, "answers": answers}, indent=1))
        if cost is not None and cost > args.max_spend:
            print(f"stopping: spent ${cost} > ${args.max_spend}")
            break
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
