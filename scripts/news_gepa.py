#!/usr/bin/env python3
"""GEPA-style tuning of Levy News's verdict prompt, on evidence the pilot already gathered.

GEPA (reflective prompt evolution) improves a prompt by reflection: run it on a
few claims, show a stronger model the mistakes next to the right answers and the
fact-checker's note, ask it for better general instructions, and keep the new
prompt only if it does better. Parents are drawn from the Pareto front (every
prompt that is best on at least one claim), so an idea that fixes a few claims
is not lost to the average. This is a small version with no extra dependencies.

The pilot's dossiers (Haiku evidence) are reused, so no web searches are bought.
Claims split as in the pilot: 60% to tune on, 40% held out and judged once at the
end, by the seed prompt and the best prompt side by side.

  backend/.venv/bin/python scripts/news_gepa.py --pilot DIR --out DIR --judge claude-sonnet-5-5 [--iterations 8] [--budget 9]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import importlib.util
import json
import random
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("news_pilot", REPO / "scripts" / "news_pilot.py")
np = importlib.util.module_from_spec(spec)
spec.loader.exec_module(np)

REFLECTOR = "claude-opus-5-5"
np.PRICES[REFLECTOR] = (4.00, 20.00, 0.20, 5.00)
MINIBATCH = 8
DANGEROUS = {"False", "Misleading"}            # rating one of these True is the error that matters most


def score(gold: str, pred: str) -> int:
    if gold in DANGEROUS and pred == "True":
        return -1
    return int(gold == pred)


def user_text(claim: dict, dossier: dict) -> str:
    lines = [f"Evidence summary: {dossier.get('summary', '')}", "", "Sources:"]
    for i, s in enumerate(dossier.get("sources") or [], 1):
        lines.append(f"{i}. [{s.get('source_type')}, {s.get('stance')}] {s.get('publisher')} ({s.get('date')}) {s.get('url')}\n   \"{s.get('quote')}\"")
    if not dossier.get("sources"):
        lines.append("(none found)")
    return (f"Claim (circulated around {claim.get('claim_date') or 'an unknown date'}):\n{claim['claim']}\n\n"
            + "\n".join(lines) + "\n\n" + np.FRAMINGS[0])


def verdict(cl, ledger, prompt: str, rec: dict, model: str, step: str) -> dict:
    ledger.check(0.08 if model == np.SONNET else 0.01)
    resp = cl.messages.create(model=model, max_tokens=6000, system=prompt,
                              messages=[{"role": "user", "content": user_text(rec["claim"], rec["dossier"])}],
                              output_config={"effort": "medium", "format": {"type": "json_schema", "schema": np.VERDICT_SCHEMA}})
    ledger.add(model, resp.usage, step, rec["claim"]["id"])
    if resp.stop_reason != "end_turn":
        return {"label": "Unproven", "confidence": 0, "reasoning": f"(stopped: {resp.stop_reason})"}
    v = json.loads(np.text_of(resp.content))
    v["confidence"] = max(0, min(100, int(v["confidence"])))
    return v


def evaluate(cl, ledger, prompt: str, recs: list[dict], model: str, step: str) -> dict[str, dict]:
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        outs = list(pool.map(lambda r: verdict(cl, ledger, prompt, r, model, step), recs))
    return {r["claim"]["id"]: o for r, o in zip(recs, outs)}


REFLECT = """You are improving the instructions that a model follows to judge claims that circulated in Zambia, using only an evidence dossier. The instructions below were used, and the model got the following claims wrong. Each example shows the claim, the evidence summary, the model's label and reasoning, the label an experienced fact-checker gave, and the fact-checker's note.

Write improved instructions that would lead to the right label in cases like these. Rules:
- Keep the four labels exactly as named: True, Misleading, False, Unproven, and keep a one-line definition of each.
- Keep the sentence saying that confidence is an estimate, from 0 to 100, that an experienced fact-checker would give the same label, and the limit of 120 words on the reasoning.
- Fix the general patterns behind the mistakes, such as how to treat a lack of evidence, partly true claims, or old claims. Do not mention any example's people, places, numbers or events.
- Never make it easier to rate a false or misleading claim True.
- Stay under 400 words. Write plain instructions, not a list of the examples.

Current instructions:
<instructions>
{prompt}
</instructions>

Mistakes:
{examples}

Return only the new instructions inside <instructions></instructions> tags."""


def reflect(cl, ledger, prompt: str, failures: list[tuple[dict, dict]]) -> str | None:
    ex = []
    for rec, out in failures:
        c = rec["claim"]
        ex.append(f"- Claim: {c['claim']}\n  Evidence summary: {rec['dossier'].get('summary', '')}\n"
                  f"  Model said: {out.get('label')} ({out.get('confidence')}%): {out.get('reasoning', '')[:600]}\n"
                  f"  Fact-checker's label: {c['label']} ({c.get('label_source', '')}). Note: {c.get('notes', '')[:400]}")
    ledger.check(0.30)
    resp = cl.messages.create(model=REFLECTOR, max_tokens=8000, output_config={"effort": "high"},
                              messages=[{"role": "user", "content": REFLECT.format(prompt=prompt, examples="\n\n".join(ex))}])
    ledger.add(REFLECTOR, resp.usage, "reflect", "-")
    m = re.search(r"<instructions>\s*(.*?)\s*</instructions>", np.text_of(resp.content), re.S)
    return m.group(1).strip() if m else None


def mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def pareto_pick(cands: list[dict], dev_ids: list[str], rng: random.Random) -> dict:
    """Pick a parent in proportion to the claims on which it is (jointly) best."""
    wins = {i: 0 for i in range(len(cands))}
    for cid in dev_ids:
        best = max(c["scores"][cid] for c in cands)
        for i, c in enumerate(cands):
            if c["scores"][cid] == best:
                wins[i] += 1
    pool = [i for i, w in wins.items() for _ in range(w)]
    return cands[rng.choice(pool)] if pool else cands[0]


def summarise(name: str, recs: list[dict], outs: dict[str, dict]) -> dict:
    pairs = [(r["claim"]["label"], outs[r["claim"]["id"]]["label"]) for r in recs]
    macro, per = np.f1s(pairs)
    return {"name": name, "n": len(pairs), "accuracy": mean(g == p for g, p in pairs), "macro_f1": macro,
            "per_label_f1": per, "false_or_misleading_rated_true": sum(1 for g, p in pairs if g in DANGEROUS and p == "True"),
            "true_rated_false": sum(1 for g, p in pairs if g == "True" and p == "False")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", required=True, help="the pilot's output folder (with claims/)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--judge", default=np.SONNET, choices=[np.SONNET, np.HAIKU])
    ap.add_argument("--iterations", type=int, default=8)
    ap.add_argument("--budget", type=float, default=9.0)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ledger = np.Ledger(out / "ledger.jsonl", args.budget)
    cl = np.client()
    rng = random.Random(args.seed)

    recs = []
    for p in sorted((Path(args.pilot) / "claims").glob("*.json")):
        r = json.loads(p.read_text())
        ev = r["evidence"].get(np.HAIKU)
        if ev and ev.get("dossier") is not None:
            recs.append({"claim": r["claim"], "dossier": ev["dossier"], "pilot": r["verdicts"].get(f"{np.HAIKU}>{args.judge}", [])})
    dev = [r for r in recs if np.is_dev(r["claim"]["id"])]
    test = [r for r in recs if not np.is_dev(r["claim"]["id"])]
    dev_ids = [r["claim"]["id"] for r in dev]
    by_id = {r["claim"]["id"]: r for r in recs}
    print(f"judge {args.judge}: {len(dev)} claims to tune on, {len(test)} held out; budget ${args.budget:.2f}", flush=True)

    # The seed prompt's dev results come from the pilot, which used the same prompt and framing.
    seed_outs = {r["claim"]["id"]: r["pilot"][0] for r in dev if r["pilot"] and "label" in r["pilot"][0]}
    missing = [r for r in dev if r["claim"]["id"] not in seed_outs]
    seed_outs.update(evaluate(cl, ledger, np.VERDICT_SYSTEM, missing, args.judge, "seed_dev") if missing else {})
    cands = [{"id": 0, "parent": None, "prompt": np.VERDICT_SYSTEM, "outs": seed_outs,
              "scores": {cid: score(by_id[cid]["claim"]["label"], seed_outs[cid]["label"]) for cid in dev_ids}}]
    log = []
    try:
        for it in range(1, args.iterations + 1):
            parent = pareto_pick(cands, dev_ids, rng)
            batch = rng.sample(dev_ids, MINIBATCH)
            fails = [(by_id[c], parent["outs"][c]) for c in batch if parent["scores"][c] < 1]
            if not fails:
                log.append({"iteration": it, "parent": parent["id"], "result": "no mistakes in minibatch"})
                continue
            child_prompt = reflect(cl, ledger, parent["prompt"], fails)
            if not child_prompt:
                log.append({"iteration": it, "parent": parent["id"], "result": "reflection gave no instructions"})
                continue
            mb = evaluate(cl, ledger, child_prompt, [by_id[c] for c in batch], args.judge, f"mb{it}")
            child_mb = mean(score(by_id[c]["claim"]["label"], mb[c]["label"]) for c in batch)
            parent_mb = mean(parent["scores"][c] for c in batch)
            entry = {"iteration": it, "parent": parent["id"], "minibatch": f"{parent_mb:.2f} -> {child_mb:.2f}"}
            if child_mb <= parent_mb:
                log.append({**entry, "result": "rejected on minibatch"})
                print(f"[{it}] rejected ({parent_mb:.2f} -> {child_mb:.2f}), spent ${ledger.spent:.2f}", flush=True)
                continue
            rest = evaluate(cl, ledger, child_prompt, [by_id[c] for c in dev_ids if c not in mb], args.judge, f"dev{it}")
            outs = {**mb, **rest}
            child = {"id": len(cands), "parent": parent["id"], "prompt": child_prompt, "outs": outs,
                     "scores": {cid: score(by_id[cid]["claim"]["label"], outs[cid]["label"]) for cid in dev_ids}}
            cands.append(child)
            log.append({**entry, "result": "accepted", "candidate": child["id"], "dev_score": mean(child["scores"].values())})
            print(f"[{it}] candidate {child['id']} dev score {mean(child['scores'].values()):.3f} "
                  f"(seed {mean(cands[0]['scores'].values()):.3f}), spent ${ledger.spent:.2f}", flush=True)
    except np.BudgetStop as e:
        print(f"!! budget stop: {e}", flush=True)

    best = max(cands, key=lambda c: (mean(c["scores"].values()), -sum(1 for v in c["scores"].values() if v < 0)))
    (out / "candidates.json").write_text(json.dumps([{k: v for k, v in c.items() if k != "outs"} for c in cands], indent=1))
    (out / "log.json").write_text(json.dumps(log, indent=1))
    lines = [f"# GEPA tuning, judge {args.judge}", "",
             f"{len(cands) - 1} improved prompts accepted over {args.iterations} iterations; best is candidate {best['id']}.",
             f"Dev score (1 right, 0 wrong, -1 for rating a false claim True): seed {mean(cands[0]['scores'].values()):.3f}, best {mean(best['scores'].values()):.3f}.", ""]
    if best["id"] != 0:
        try:
            seed_test = evaluate(cl, ledger, np.VERDICT_SYSTEM, test, args.judge, "seed_test")
            best_test = evaluate(cl, ledger, best["prompt"], test, args.judge, "best_test")
            a, b = summarise("seed prompt", test, seed_test), summarise("tuned prompt", test, best_test)
            (out / "test.json").write_text(json.dumps({"seed": a, "best": b, "seed_outs": seed_test, "best_outs": best_test}, indent=1))
            lines += [f"## Held-out claims ({len(test)})", ""]
            for s in (a, b):
                lines.append(f"- {s['name']}: accuracy {s['accuracy']:.0%}, macro-F1 {s['macro_f1']:.2f}, "
                             f"false or misleading rated True {s['false_or_misleading_rated_true']}, true rated False {s['true_rated_false']}; "
                             "F1 " + ", ".join(f"{k} {v:.2f}" for k, v in s["per_label_f1"].items()))
        except np.BudgetStop as e:
            lines.append(f"Held-out test skipped: {e}")
        lines += ["", "## Tuned instructions", "", "```", best["prompt"], "```"]
    else:
        lines.append("No prompt beat the seed on the tuning claims, so the held-out claims were not used.")
    lines += ["", f"Spent ${ledger.spent:.2f}."]
    (out / "report.md").write_text("\n".join(lines))
    print("\n".join(lines), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
