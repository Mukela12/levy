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
from app.services import agent, kimi, openrouter  # noqa: E402

# Dollars per million tokens: input, output, cache write (5 min), cache read.
# Claude from the Anthropic price list; Kimi from Moonshot's, 6 Oct 2026.
PRICES = {
    "claude-sonnet-4-6": (3.00, 15.00, 3.75, 0.30),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.20),
    "claude-haiku-4-5": (1.00, 5.00, 1.25, 0.10),
    "kimi-k2.6": (0.95, 4.00, 0.95, 0.16),
    "kimi-k3": (0.95, 14.00, 0.95, 0.31),
}
CALLS: list[dict] = []


def _tap_usage() -> None:
    """Record every model call's usage, cache included, to price a run.

    The agent's done event counts only uncached input, which under-reports a
    Claude run whose prefix is read from cache on every round.
    """
    real = agent.anthropic.AsyncAnthropic

    class Tap:
        def __init__(self, **kw):
            self._c = real(**kw)
            self.messages = self

        def stream(self, **kw):
            cm = self._c.messages.stream(**kw)

            class CM:
                async def __aenter__(s):
                    st = await cm.__aenter__()
                    orig = st.get_final_message

                    async def final():
                        m = await orig()
                        u = m.usage
                        CALLS.append({"model": kw["model"], "in": u.input_tokens or 0, "out": u.output_tokens or 0,
                                      "cw": getattr(u, "cache_creation_input_tokens", 0) or 0,
                                      "cr": getattr(u, "cache_read_input_tokens", 0) or 0})
                        return m
                    st.get_final_message = final
                    return st

                async def __aexit__(s, *a):
                    return await cm.__aexit__(*a)
            return CM()
    agent.anthropic.AsyncAnthropic = lambda **kw: Tap(**kw)

    real_final = kimi._to_final_message

    def kimi_final(payload):
        u = payload.get("usage") or {}
        cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or u.get("cached_tokens", 0) or 0
        CALLS.append({"model": payload.get("model") or "kimi", "in": (u.get("prompt_tokens") or 0) - cached,
                      "out": u.get("completion_tokens") or 0, "cw": 0, "cr": cached})
        return real_final(payload)
    kimi._to_final_message = kimi_final


def cost(calls: list[dict], model: str) -> float:
    p = PRICES.get(model)
    if not p:
        return 0.0
    return sum(c["in"] * p[0] + c["out"] * p[1] + c["cw"] * p[2] + c["cr"] * p[3] for c in calls) / 1e6


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
    ap.add_argument("--effort", help="agent_effort for adaptive-thinking models (low|medium|high|xhigh|max)")
    ap.add_argument("--label", help="suffix for the results file, e.g. medium")
    args = ap.parse_args()

    s = get_settings()
    if args.effort:
        s.agent_effort = args.effort
    _tap_usage()
    # Cut the chain to the model asked for: no Claude fallbacks, no Kimi
    # unless it is the model under test, and for an OpenRouter model no hop
    # to the free router either.
    agent.FALLBACK_MODELS = []
    if kimi.is_kimi_model(args.model):
        s.kimi_fallback_model = args.model
    else:
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
    slug = re.sub(r"[^a-z0-9.]+", "-", args.model.lower()).strip("-") + (f"-{args.label}" if args.label else "")
    out_path = args.out or ROOT / "results" / f"{date}-levy-{slug}.json"

    spent0 = openrouter_spend()
    answers = []
    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q['id']}", flush=True)
        before = len(CALLS)
        try:
            a = asyncio.run(ask(q["question"], args.model))
        except Exception as e:  # noqa: BLE001 — one bad question must not lose the run
            a = {"answer": "", "error": f"{type(e).__name__}: {e}"[:300]}
        mine = CALLS[before:]
        a["model_calls"] = len(mine)
        a["usage"] = {k: sum(c[k] for c in mine) for k in ("in", "out", "cw", "cr")}
        a["cost_usd"] = round(cost(mine, args.model), 4)
        answers.append({"id": q["id"], **a})
        spent = openrouter_spend()
        cost_total = round(sum(x.get("cost_usd") or 0 for x in answers), 4) if args.model in PRICES else (
            None if spent0 is None or spent is None else round(spent - spent0, 4))
        print(f"    {len(a['answer'])} chars, {a.get('seconds')}s, {a.get('tool_calls')} tools, {a['model_calls']} calls, "
              f"${a['cost_usd']}, by {a.get('answered_by')}, spent so far ${cost_total}"
              + (f", ERROR {a['error']}" if a.get("error") else ""), flush=True)
        out_path.write_text(json.dumps({"model": f"levy-{slug}", "date": date, "api": "local",
                                        "effort": s.agent_effort, "spent_usd": cost_total, "answers": answers}, indent=1))
        if cost_total is not None and cost_total > args.max_spend:
            print(f"stopping: spent ${cost_total} > ${args.max_spend}")
            break
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
