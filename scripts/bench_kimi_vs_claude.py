#!/usr/bin/env python3
"""Benchmark Kimi against Claude on Levy's ACTUAL workload.

Not a synthetic test: this loads Levy's real system prompt and real tool
schemas, then replays questions taken verbatim from the field study. What we
need to know is not "is Kimi smart" but three specific things:

  1. Does it emit well-formed tool calls against OUR 27-tool schema? Levy is a
     tool-calling agent; a model that answers from memory instead of searching
     the corpus is useless here no matter how cheap it is.
  2. Does it pick the RIGHT tool, with the right arguments?
  3. What does a real Levy turn actually cost on each model?

Run:  python scripts/bench_kimi_vs_claude.py
Needs MOONSHOT_API_KEY and ANTHROPIC_API_KEY in the environment.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv

load_dotenv(REPO / "backend" / ".env")

from app.services import tools as levy_tools
from app.services.agent import SYSTEM_PROMPT, AGENT_SYSTEM_SUFFIX

import httpx

MOONSHOT_KEY = os.environ.get("MOONSHOT_API_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# USD per 1M tokens (direct first-party APIs, Aug 2026).
PRICING = {
    "kimi-k2.6":            {"in": 0.95, "cache_read": 0.16, "out": 4.00},
    "kimi-k2.7-code":       {"in": 0.95, "cache_read": 0.19, "out": 4.00},
    "claude-sonnet-4-6":    {"in": 3.00, "cache_read": 0.30, "out": 15.00},
    "claude-haiku-4-5":     {"in": 1.00, "cache_read": 0.10, "out": 5.00},
}

# Verbatim from the field study — these are questions real users actually asked.
CASES = [
    {
        "id": "redundancy",
        "why": "Employer/HR audience. MUST call calculate_entitlements, not do maths.",
        "q": ("HI Please can you assist me with a redundancy package. Salary 61050, "
              "Leave days 8.67, Start date 22/09/2025, termination date 4 September 2026. "
              "Contract type is permanent."),
        "want_tool": "calculate_entitlements",
    },
    {
        "id": "penalty_units",
        "why": "Must search the corpus for the penalty-unit value, not guess a number.",
        "q": "who gets the fine k160,000? and how do penalty units convert to kwacha in Zambia?",
        "want_tool": "search_corpus",
    },
    {
        "id": "intermeddling",
        "why": "Pure Zambian statute lookup. Must search rather than answer from memory.",
        "q": "what is considered intermeddling in zambia",
        "want_tool": "search_corpus",
    },
    {
        "id": "draft_doc",
        "why": "Document request — should reach for a drafting tool, not prose.",
        "q": ("i was asking you to provide a document, just a generic template for a "
              "notice of intention to sue my former employer"),
        "want_tool": None,  # any draft_* tool counts
    },
]


def _levy_tools_json():
    reg = levy_tools.build_tool_registry(owner_id="bench", session_id=None)
    out = []
    for name, t in reg.items():
        out.append({"type": "function", "function": {
            "name": name, "description": t.description, "parameters": t.input_schema}})
    return out, len(reg)


TOOLS_OPENAI, N_TOOLS = _levy_tools_json()
SYSTEM = SYSTEM_PROMPT + AGENT_SYSTEM_SUFFIX


def run_kimi(model: str, case: dict) -> dict:
    t0 = time.time()
    try:
        r = httpx.post(
            "https://api.moonshot.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {MOONSHOT_KEY}"},
            json={
                "model": model,
                "messages": [{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": case["q"]}],
                "tools": TOOLS_OPENAI,
                "max_tokens": 3000,
                # NOTE: kimi-k2.6 is a reasoning model and rejects any
                # temperature but 1 ("invalid temperature: only 1 is allowed
                # for this model") — same constraint as Claude Opus 4.7+.
            },
            timeout=300.0,
        )
        r.raise_for_status()
        d = r.json()
    except Exception as e:  # noqa: BLE001
        body = ""
        if isinstance(e, httpx.HTTPStatusError):
            body = e.response.text[:300]
        return {"error": f"{type(e).__name__}: {e} {body}"}
    msg = d["choices"][0]["message"]
    u = d.get("usage", {}) or {}
    calls = msg.get("tool_calls") or []
    return {
        "secs": round(time.time() - t0, 1),
        "tools": [c["function"]["name"] for c in calls],
        "args": [c["function"]["arguments"][:300] for c in calls],
        "text": (msg.get("content") or "")[:300],
        "in_tok": u.get("prompt_tokens", 0),
        "cached": (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
        "out_tok": u.get("completion_tokens", 0),
        "reasoning_tok": (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
        "finish": d["choices"][0].get("finish_reason"),
    }


def run_claude(model: str, case: dict) -> dict:
    import anthropic

    reg = levy_tools.build_tool_registry(owner_id="bench", session_id=None)
    schemas = levy_tools.to_anthropic_schema(reg)
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    t0 = time.time()
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=3000,
            system=[{"type": "text", "text": SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            tools=schemas,
            messages=[{"role": "user", "content": case["q"]}],
        )
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
    calls = [b for b in resp.content if b.type == "tool_use"]
    text = "".join(b.text for b in resp.content if b.type == "text")
    u = resp.usage
    return {
        "secs": round(time.time() - t0, 1),
        "tools": [c.name for c in calls],
        "args": [json.dumps(c.input)[:300] for c in calls],
        "text": text[:300],
        "in_tok": u.input_tokens,
        "cached": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "out_tok": u.output_tokens,
        "reasoning_tok": 0,
        "finish": resp.stop_reason,
    }


def cost_usd(model: str, r: dict) -> float:
    p = PRICING[model]
    cached = r.get("cached", 0) or 0
    fresh_in = max(0, (r.get("in_tok", 0) or 0) - cached)
    c = fresh_in * p["in"] + cached * p["cache_read"] + (r.get("out_tok", 0) or 0) * p["out"]
    # Claude cache writes cost 1.25x base input.
    c += (r.get("cache_write", 0) or 0) * p["in"] * 1.25
    return c / 1_000_000


def main():
    models = [("kimi", "kimi-k2.6"), ("kimi", "kimi-k2.7-code"),
              ("claude", "claude-sonnet-4-6"), ("claude", "claude-haiku-4-5")]
    print(f"Levy system prompt: {len(SYSTEM):,} chars | {N_TOOLS} tools\n")
    totals: dict[str, float] = {}

    for case in CASES:
        print("=" * 78)
        print(f"CASE {case['id']}: {case['why']}")
        print(f"  Q: {case['q'][:110]}")
        want = case["want_tool"]
        for vendor, model in models:
            r = run_kimi(model, case) if vendor == "kimi" else run_claude(model, case)
            if "error" in r:
                print(f"  {model:20} ERROR {r['error'][:150]}")
                continue
            c = cost_usd(model, r)
            totals[model] = totals.get(model, 0.0) + c
            if want:
                ok = "HIT " if want in r["tools"] else "MISS"
            else:
                ok = "HIT " if any(t.startswith("draft_") for t in r["tools"]) else "MISS"
            reason = f" (+{r['reasoning_tok']} reasoning)" if r["reasoning_tok"] else ""
            print(f"  {model:20} {ok} {r['secs']:>5.1f}s  "
                  f"in={r['in_tok']:>6,} cached={r['cached']:>6,} out={r['out_tok']:>5,}{reason}  "
                  f"${c:.5f}  tools={r['tools'][:3]}")
            if r["tools"] and r["args"]:
                print(f"       args: {r['args'][0][:150]}")
            elif r["text"]:
                print(f"       text: {r['text'][:130]}")
        print()

    print("=" * 78)
    print("TOTAL over all cases (uncached first-call pricing):")
    for m, c in sorted(totals.items(), key=lambda kv: kv[1]):
        print(f"  {m:22} ${c:.5f}")


if __name__ == "__main__":
    main()
