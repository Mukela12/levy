#!/usr/bin/env python3
"""Levy News accuracy pilot: how well Levy judges Zambian claims, and with which models.

One run answers three questions on a labelled set of claims:
  1. Evidence: does Sonnet 5.5 find better evidence than Haiku 5.5?
  2. Verdict: Haiku against Sonnet, one judgement against five varied ones.
  3. Confidence: is a model's stated confidence calibrated, and does agreement
     across five runs, fitted on part of the set, calibrate better?

Fact-checkers' own sites are blocked in search and fetch, so a verdict comes from
the underlying evidence and not from a published rating. Each call's cost is
worked out from its usage and appended to OUT/ledger.jsonl; the run stops before
the budget. Results are saved per claim, so a rerun skips finished work.

  backend/.venv/bin/python scripts/news_pilot.py run --claims CLAIMS.jsonl --out DIR [--limit N] [--sonnet-evidence 40] [--budget 45]
  backend/.venv/bin/python scripts/news_pilot.py report --claims CLAIMS.jsonl --out DIR
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import importlib.util
import json
import math
import random
import re
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HAIKU, SONNET = "claude-haiku-5-5", "claude-sonnet-5-5"
LABELS = ["True", "Misleading", "False", "Unproven"]

# $ per million tokens: input, output, cache read, cache write (5 minutes). Haiku 5.5's
# rates apply to prompts up to 100K tokens; longer prompts cost $0.50 / $2.50.
PRICES = {HAIKU: (0.10, 0.50, 0.01, 0.125), SONNET: (2.00, 10.00, 0.20, 2.50)}
HAIKU_LONG = (0.50, 2.50)
SEARCH_COST = 10.0 / 1000           # web search, per search; web fetch adds only tokens

FACT_CHECK_HOSTS = [
    "factcheck.afp.com", "africacheck.org", "pesacheck.org", "iverifyzambia.org", "fullfact.org",
    "snopes.com", "politifact.com", "leadstories.com", "dubawa.org", "misbar.com", "factcheck.org",
    "checkyourfact.com", "logicallyfacts.com", "factcheckhub.com", "toolbox.google.com",
    "truthorfiction.com", "factly.in", "boomlive.in", "stopfake.org", "healthfeedback.org",
    "makanday.org", "acazambia.org", "namibiafactcheck.org.na", "newsverifierafrica.com",
    "zambialii.org",            # Levy never scrapes ZambiaLII; official sources instead
]
FACT_CHECK_PATH = re.compile(r"fact-?check|factcheck|/reality[-_]check|/verify/", re.I)


# ---------------------------------------------------------------- budget ledger

class BudgetStop(Exception):
    pass


class Ledger:
    def __init__(self, path: Path, budget: float):
        self.path, self.budget, self.lock = path, budget, threading.Lock()
        self.spent = 0.0
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    self.spent += json.loads(line)["cost"]

    def check(self, reserve: float) -> None:
        with self.lock:
            if self.spent + reserve > self.budget:
                raise BudgetStop(f"spent ${self.spent:.2f} of ${self.budget:.2f}; next call could pass it")

    def add(self, model: str, usage, step: str, claim_id: str) -> float:
        cost = usage_cost(model, usage)
        rec = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": model, "step": step, "claim": claim_id,
               "cost": round(cost, 6), "in": usage.input_tokens, "out": usage.output_tokens,
               "cache_read": usage.cache_read_input_tokens or 0, "cache_write": usage.cache_creation_input_tokens or 0,
               "searches": searches_of(usage)}
        with self.lock:
            self.spent += cost
            with self.path.open("a") as f:
                f.write(json.dumps(rec) + "\n")
        return cost


def searches_of(usage) -> int:
    stu = getattr(usage, "server_tool_use", None)
    return int(getattr(stu, "web_search_requests", 0) or 0) if stu else 0


def usage_cost(model: str, usage) -> float:
    p_in, p_out, p_read, p_write = PRICES[model]
    read, write = usage.cache_read_input_tokens or 0, usage.cache_creation_input_tokens or 0
    if model == HAIKU and usage.input_tokens + read + write > 100_000:
        p_in, p_out = HAIKU_LONG
        p_read, p_write = p_in * 0.1, p_in * 1.25
    return (usage.input_tokens * p_in + usage.output_tokens * p_out + read * p_read + write * p_write) / 1e6 \
        + searches_of(usage) * SEARCH_COST


# ---------------------------------------------------------------- the model calls

def client():
    import anthropic
    key = next((line.split("=", 1)[1].strip().strip('"').strip("'")
                for line in (REPO / "backend" / ".env").read_text().splitlines()
                if line.startswith("ANTHROPIC_API_KEY=")), None)
    return anthropic.Anthropic(api_key=key, max_retries=4, timeout=300.0)


def web_tools(model: str) -> list[dict]:
    # Basic tool versions on both models: same behaviour, and no code-execution
    # filtering to price, so the two evidence runs compare fairly.
    return [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 5, "blocked_domains": FACT_CHECK_HOSTS},
        {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 3, "blocked_domains": FACT_CHECK_HOSTS},
    ]


EVIDENCE_SYSTEM = """You gather evidence about a claim that circulated in Zambia, for a fact-checker who will judge it later.

Look for the most authoritative sources first: official Zambian bodies (ministries, State House, the Bank of Zambia, ZRA, Parliament, the Judiciary, the Electoral Commission of Zambia, ZNPHI, the Government Gazette), then established news outlets, then primary documents and data. Do not use fact-checking websites or articles that rate the claim; find the underlying evidence yourself. Note when a source is much later or earlier than the claim. Include evidence that cuts both ways, and say plainly when you could not find something.

Do not give a verdict. End your reply with the dossier as JSON inside <dossier></dossier> tags:
{"summary": "two or three sentences on what the evidence shows and what is missing",
 "sources": [{"url": "...", "publisher": "...", "date": "YYYY-MM-DD or unknown", "source_type": "official|news|social|document|other",
              "quote": "a verbatim excerpt under 40 words that bears on the claim", "stance": "supports|contradicts|neutral"}]}"""

DOSSIER_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["summary", "sources"],
    "properties": {
        "summary": {"type": "string"},
        "sources": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["url", "publisher", "date", "source_type", "quote", "stance"],
            "properties": {
                "url": {"type": "string"}, "publisher": {"type": "string"}, "date": {"type": "string"},
                "source_type": {"type": "string", "enum": ["official", "news", "social", "document", "other"]},
                "quote": {"type": "string"}, "stance": {"type": "string", "enum": ["supports", "contradicts", "neutral"]},
            }}},
    },
}

VERDICT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["label", "confidence", "reasoning"],
    "properties": {
        "label": {"type": "string", "enum": LABELS},
        "confidence": {"type": "integer"},          # structured outputs take no bounds; clamped below
        "reasoning": {"type": "string"},
    },
}

VERDICT_SYSTEM = """You judge claims that circulated in Zambia, using only the evidence dossier you are given.

Labels:
- True: the evidence supports the claim as stated.
- Misleading: partly accurate, or missing context that changes what it means.
- False: the evidence contradicts it.
- Unproven: the evidence is not enough to say either way.

Confidence is your estimate, from 0 to 100, that an experienced fact-checker would give the same label. Keep the reasoning under 120 words."""

FRAMINGS = [
    "Weigh the evidence and give your verdict.",
    "Before deciding, set out the strongest case that the claim is accurate. Then weigh it against the evidence and give your verdict.",
    "Before deciding, set out the strongest case that the claim is false or misleading. Then weigh it against the evidence and give your verdict.",
    "Before deciding, set out the strongest case that the claim is accurate. Then weigh it against the evidence and give your verdict.",
    "Before deciding, set out the strongest case that the claim is false or misleading. Then weigh it against the evidence and give your verdict.",
]


def text_of(content) -> str:
    return "".join(getattr(b, "text", "") for b in content if getattr(b, "type", "") == "text")


def gather_evidence(cl, ledger: Ledger, claim: dict, model: str) -> dict:
    user = f"Claim (circulated around {claim.get('claim_date') or 'an unknown date'}):\n{claim['claim']}"
    messages = [{"role": "user", "content": user}]
    cost = 0.0
    searches = 0
    for _ in range(4):                                    # first call plus up to three pause_turn resumes
        ledger.check(0.60 if model == SONNET else 0.15)
        resp = cl.messages.create(model=model, max_tokens=12000, system=EVIDENCE_SYSTEM, messages=messages,
                                  tools=web_tools(model), output_config={"effort": "medium"})
        cost += ledger.add(model, resp.usage, "evidence", claim["id"])
        searches += searches_of(resp.usage)
        if resp.stop_reason == "pause_turn":
            messages = [{"role": "user", "content": user}, {"role": "assistant", "content": resp.content}]
            continue
        break
    raw = text_of(resp.content)
    m = re.search(r"<dossier>\s*(\{.*\})\s*</dossier>", raw, re.S)
    dossier = None
    if m:
        try:
            dossier = json.loads(m.group(1))
        except json.JSONDecodeError:
            dossier = None
    if dossier is None:                                   # one cheap repair pass with a strict schema
        ledger.check(0.05)
        fix = cl.messages.create(model=HAIKU, max_tokens=6000, output_config={"effort": "low", "format": {"type": "json_schema", "schema": DOSSIER_SCHEMA}},
                                 messages=[{"role": "user", "content": "Turn this research note into the dossier JSON. Keep URLs and quotes exactly as written.\n\n" + raw[-20000:]}])
        cost += ledger.add(HAIKU, fix.usage, "dossier_repair", claim["id"])
        dossier = json.loads(text_of(fix.content))
    return {"model": model, "dossier": dossier, "stop_reason": resp.stop_reason, "searches": searches, "cost": round(cost, 5)}


def shuffled(sources: list, seed: str) -> list:
    out = list(sources)
    random.Random(seed).shuffle(out)
    return out


def judge(cl, ledger: Ledger, claim: dict, dossier: dict, model: str, run: int) -> dict:
    sources = dossier.get("sources") or []
    if run:
        sources = shuffled(sources, f"{claim['id']}-{run}")
    lines = [f"Evidence summary: {dossier.get('summary', '')}", "", "Sources:"]
    for i, s in enumerate(sources, 1):
        lines.append(f"{i}. [{s.get('source_type')}, {s.get('stance')}] {s.get('publisher')} ({s.get('date')}) {s.get('url')}\n   \"{s.get('quote')}\"")
    if not sources:
        lines.append("(none found)")
    user = (f"Claim (circulated around {claim.get('claim_date') or 'an unknown date'}):\n{claim['claim']}\n\n"
            + "\n".join(lines) + "\n\n" + FRAMINGS[run])
    ledger.check(0.08 if model == SONNET else 0.01)
    resp = cl.messages.create(model=model, max_tokens=6000, system=VERDICT_SYSTEM,
                              messages=[{"role": "user", "content": user}],
                              output_config={"effort": "medium", "format": {"type": "json_schema", "schema": VERDICT_SCHEMA}})
    cost = ledger.add(model, resp.usage, f"verdict{run}", claim["id"])
    if resp.stop_reason != "end_turn":
        return {"model": model, "run": run, "error": resp.stop_reason, "cost": round(cost, 5)}
    v = json.loads(text_of(resp.content))
    v["confidence"] = max(0, min(100, int(v["confidence"])))
    return {"model": model, "run": run, **v, "cost": round(cost, 5)}


# ---------------------------------------------------------------- the run

def load_claims(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [r for r in rows if r.get("label") in LABELS and r.get("claim")]


def subset(claims: list[dict], n: int) -> set[str]:
    """A stable, label-balanced subset for the costlier Sonnet evidence runs."""
    by = {lab: sorted((c for c in claims if c["label"] == lab), key=lambda c: hashlib.sha1(c["id"].encode()).hexdigest()) for lab in LABELS}
    picked: list[str] = []
    while len(picked) < n and any(by.values()):
        for lab in LABELS:
            if by[lab] and len(picked) < n:
                picked.append(by[lab].pop(0)["id"])
    return set(picked)


def run(args) -> int:
    out = Path(args.out)
    (out / "claims").mkdir(parents=True, exist_ok=True)
    ledger = Ledger(out / "ledger.jsonl", args.budget)
    claims = load_claims(Path(args.claims))[: args.limit or None]
    sonnet_ids = subset(claims, args.sonnet_evidence)
    cl = client()
    print(f"{len(claims)} claims; Sonnet also gathers evidence for {len(sonnet_ids)}; spent so far ${ledger.spent:.2f} of ${args.budget:.2f}", flush=True)

    def work(c: dict) -> str:
        path = out / "claims" / f"{c['id']}.json"
        rec = json.loads(path.read_text()) if path.exists() else {"claim": c, "evidence": {}, "verdicts": {}}
        plan = [(HAIKU, [HAIKU, SONNET])] + ([(SONNET, [HAIKU, SONNET])] if c["id"] in sonnet_ids else [])
        for ev_model, judges in plan:
            if ev_model not in rec["evidence"]:
                rec["evidence"][ev_model] = gather_evidence(cl, ledger, c, ev_model)
                path.write_text(json.dumps(rec, indent=1))
            dossier = rec["evidence"][ev_model]["dossier"]
            for jm in judges:
                key = f"{ev_model}>{jm}"
                runs = rec["verdicts"].setdefault(key, [])
                while len(runs) < 5:
                    runs.append(judge(cl, ledger, c, dossier, jm, len(runs)))
                    path.write_text(json.dumps(rec, indent=1))
        return c["id"]

    done = 0
    try:
        with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = [pool.submit(work, c) for c in claims]
            for f in cf.as_completed(futs):
                try:
                    f.result()
                    done += 1
                except BudgetStop as e:
                    print(f"!! budget stop: {e}", flush=True)
                    for g in futs:
                        g.cancel()
                    break
                except Exception as e:  # noqa: BLE001  one bad claim must not sink the run
                    print(f"!! claim failed: {str(e)[:160]}", flush=True)
                if done and done % 10 == 0:
                    print(f"[{done}/{len(claims)}] spent ${ledger.spent:.2f}", flush=True)
    finally:
        print(f"SUMMARY claims done {done}/{len(claims)}, spent ${ledger.spent:.2f}", flush=True)
    return 0


# ---------------------------------------------------------------- the report

def majority(runs: list[dict]) -> tuple[str, float, float]:
    good = [r for r in runs if "label" in r]
    if not good:
        return "Unproven", 0.0, 0.0
    counts = {lab: sum(1 for r in good if r["label"] == lab) for lab in LABELS}
    top = max(LABELS, key=lambda lab: (counts[lab], -LABELS.index(lab)))
    agree = counts[top] / len(good)
    conf = sum(r["confidence"] for r in good if r["label"] == top) / max(1, counts[top]) / 100
    return top, agree, conf


def f1s(pairs: list[tuple[str, str]]) -> tuple[float, dict]:
    per = {}
    for lab in LABELS:
        tp = sum(1 for g, p in pairs if g == lab and p == lab)
        fp = sum(1 for g, p in pairs if g != lab and p == lab)
        fn = sum(1 for g, p in pairs if g == lab and p != lab)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        per[lab] = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    present = [lab for lab in LABELS if any(g == lab for g, _ in pairs)]
    return (sum(per[lab] for lab in present) / len(present) if present else 0.0), per


def ece(probs: list[float], correct: list[int], bins: int = 10) -> float:
    total, err = len(probs), 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, p in enumerate(probs) if lo <= p < hi or (b == bins - 1 and p == 1.0)]
        if idx:
            err += len(idx) / total * abs(sum(probs[i] for i in idx) / len(idx) - sum(correct[i] for i in idx) / len(idx))
    return err


def platt(xs: list[list[float]], ys: list[int], steps: int = 4000, lr: float = 0.5) -> list[float]:
    """Logistic regression by gradient descent: small data, no numpy needed."""
    w = [0.0] * (len(xs[0]) + 1)
    for _ in range(steps):
        g = [0.0] * len(w)
        for x, y in zip(xs, ys):
            z = w[0] + sum(wi * xi for wi, xi in zip(w[1:], x))
            p = 1 / (1 + math.exp(-max(-30, min(30, z))))
            g[0] += p - y
            for j, xj in enumerate(x, 1):
                g[j] += (p - y) * xj
        w = [wi - lr * gi / len(xs) for wi, gi in zip(w, g)]
    return w


def predict(w: list[float], x: list[float]) -> float:
    z = w[0] + sum(wi * xi for wi, xi in zip(w[1:], x))
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def is_dev(claim_id: str) -> bool:
    return int(hashlib.sha1(claim_id.encode()).hexdigest(), 16) % 10 < 6      # 60% fit, 40% test


def citation_check(recs: list[dict], per_claim: int = 3) -> dict:
    """Do cited pages load, and is the quoted text on them? Uses Levy's quote matcher."""
    import httpx
    spec = importlib.util.spec_from_file_location("quote_check", REPO / "backend/app/services/quote_check.py")
    qc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qc)
    tally = {"checked": 0, "loaded": 0, "quote_found": 0, "blocked_or_failed": 0, "fact_check_urls": 0}
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
               "Accept": "text/html,application/pdf,*/*"}

    def get(url: str):
        try:
            return httpx.get(url, timeout=20, follow_redirects=True, headers=headers)
        except httpx.ConnectError as e:
            # parliament.gov.zm serves an incomplete certificate chain that browsers repair
            # and Python does not. These are public pages read once, so retry unverified.
            if "CERTIFICATE_VERIFY_FAILED" in str(e):
                return httpx.get(url, timeout=20, follow_redirects=True, headers=headers, verify=False)
            raise

    def one(src: dict) -> tuple[bool, bool]:
        if "zambialii.org" in src.get("url", ""):
            return False, False
        try:
            r = get(src["url"])
        except Exception:  # noqa: BLE001
            return False, False
        if r.status_code >= 400:
            return False, False
        if "pdf" in r.headers.get("content-type", "") or src["url"].lower().split("?")[0].endswith(".pdf"):
            import pymupdf as fitz
            with fitz.open(stream=r.content, filetype="pdf") as doc:
                text = " ".join(page.get_text() for page in doc)
        else:
            text = re.sub(r"<[^>]+>", " ", r.text)
        return True, qc.match_score(src.get("quote", ""), text) >= qc.CLOSE

    srcs = []
    for rec in recs:
        for ev in rec["evidence"].values():
            for s in (ev.get("dossier") or {}).get("sources", [])[:per_claim]:
                if FACT_CHECK_PATH.search(s.get("url", "")):
                    tally["fact_check_urls"] += 1
                srcs.append(s)
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        for loaded, found in pool.map(one, srcs):
            tally["checked"] += 1
            tally["loaded"] += loaded
            tally["quote_found"] += found
            tally["blocked_or_failed"] += not loaded
    return tally


def report(args) -> int:
    out = Path(args.out)
    recs = [json.loads(p.read_text()) for p in sorted((out / "claims").glob("*.json"))]
    spent = sum(json.loads(line)["cost"] for line in (out / "ledger.jsonl").read_text().splitlines() if line.strip())
    lines = [f"# Levy News pilot results", "", f"{len(recs)} claims, ${spent:.2f} spent.", ""]
    configs = sorted({k for r in recs for k in r["verdicts"]})
    summary = {}
    for key in configs:
        rows = [r for r in recs if len(r["verdicts"].get(key, [])) == 5]
        if not rows:
            continue
        gold = [r["claim"]["label"] for r in rows]
        single = [r["verdicts"][key][0] for r in rows]
        one = [(g, s.get("label", "Unproven")) for g, s in zip(gold, single)]
        five = [majority(r["verdicts"][key]) for r in rows]
        many = [(g, m[0]) for g, m in zip(gold, five)]
        acc1 = sum(g == p for g, p in one) / len(one)
        acc5 = sum(g == p for g, p in many) / len(many)
        mf1_1, per1 = f1s(one)
        mf1_5, per5 = f1s(many)
        # Stated confidence of the single run, against whether it was right.
        p1 = [s.get("confidence", 0) / 100 for s in single]
        y1 = [int(g == p) for g, p in one]
        # Five runs: fit on the dev part, test on the rest.
        feats = [[m[1], m[2]] for m in five]
        y5 = [int(g == p) for g, p in many]
        dev = [i for i, r in enumerate(rows) if is_dev(r["claim"]["id"])]
        test = [i for i in range(len(rows)) if i not in dev]
        w = platt([feats[i] for i in dev], [y5[i] for i in dev]) if len(dev) >= 10 else None
        cal = [predict(w, f) for f in feats] if w else [m[2] for m in five]
        test_ece_stated = ece([p1[i] for i in test], [y1[i] for i in test]) if test else float("nan")
        test_ece_cal = ece([cal[i] for i in test], [y5[i] for i in test]) if test else float("nan")
        # How many verdicts could be published at 90% accuracy, using the calibrated score.
        order = sorted(range(len(rows)), key=lambda i: -cal[i])
        cover, best = 0, 0.0
        for k in range(1, len(order) + 1):
            top = order[:k]
            a = sum(y5[i] for i in top) / k
            if a >= 0.9:
                cover, best = k, a
        cost = sum(s["cost"] for r in rows for s in r["verdicts"][key])
        ev_cost = sum(r["evidence"][key.split(">")[0]]["cost"] for r in rows)
        summary[key] = {"n": len(rows), "acc_single": acc1, "acc_five": acc5, "macro_f1_single": mf1_1, "macro_f1_five": mf1_5,
                        "per_label_f1_five": per5, "ece_stated_test": test_ece_stated, "ece_calibrated_test": test_ece_cal,
                        "publishable_at_90": cover, "verdict_cost": cost, "evidence_cost": ev_cost, "platt": w}
        lines += [f"## Evidence by {key.split('>')[0]}, judged by {key.split('>')[1]} ({len(rows)} claims)", "",
                  f"- One judgement: accuracy {acc1:.0%}, macro-F1 {mf1_1:.2f}",
                  f"- Five judgements, majority: accuracy {acc5:.0%}, macro-F1 {mf1_5:.2f}",
                  "- F1 by label (five): " + ", ".join(f"{lab} {per5[lab]:.2f}" for lab in LABELS),
                  f"- Calibration error on held-out claims: stated confidence {test_ece_stated:.3f}, calibrated five-run score {test_ece_cal:.3f}",
                  f"- Verdicts publishable at 90% accuracy: {cover} of {len(rows)}" + (f" ({best:.0%} accurate)" if cover else ""),
                  f"- Cost: evidence ${ev_cost:.2f}, verdicts ${cost:.2f} (${(ev_cost + cost) / len(rows):.3f} a claim)", ""]
    if args.citations:
        t = citation_check(recs)
        lines += ["## Citations", "",
                  f"- Sources checked: {t['checked']}; pages that loaded: {t['loaded']}; quote found on the page: {t['quote_found']}",
                  f"- Pages blocked or failed to load: {t['blocked_or_failed']}; fact-check URLs cited despite the block: {t['fact_check_urls']}", ""]
        summary["citations"] = t
    (out / "report.md").write_text("\n".join(lines))
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print("\n".join(lines))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--claims", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--sonnet-evidence", type=int, default=40)
    r.add_argument("--budget", type=float, default=45.0)
    r.add_argument("--workers", type=int, default=4)
    p = sub.add_parser("report")
    p.add_argument("--claims", required=False)
    p.add_argument("--out", required=True)
    p.add_argument("--citations", action="store_true")
    args = ap.parse_args()
    return run(args) if args.cmd == "run" else report(args)


if __name__ == "__main__":
    raise SystemExit(main())
