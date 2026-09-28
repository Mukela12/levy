#!/usr/bin/env python3
"""Does lexical search improve what Levy retrieves, and by how much?

Compares retrieval variants on the same questions, measured on the top five
results a model would actually be handed:

  dense       the production path today: pgvector cosine, threshold 0.6
  lexical     keyword ranking on its own (BM25 locally, or Postgres full-text
              search once the migration is applied)
  hybrid      dense and lexical fused with reciprocal rank fusion
  rerank      hybrid, then a cross-encoder reorders the fused shortlist

Metrics, per question with a known answer:

  act@5       the expected Act appears in the top five
  sec@5       a chunk from the expected Act AND an expected section appears
  p@5         share of the top five that come from the expected Act
  mrr         1 / rank of the first chunk with the expected section
  terms       share of the expected keywords present in the top five's text
              (the "expected-terms rate"; diagnostic, not proof of correctness)

The local BM25 variant is a prototype: it scores a copy of the library's chunk
text on this machine. It is real BM25, which Postgres full-text search is not,
so it shows what lexical ranking can add before anything is deployed. The
`--lexical pg` variant measures the thing that would actually ship.

Every variant gets production's repealed-Act demotion (at most two matches
from a repealed Act), so no variant wins by surfacing dead law.

  python bench/retrieval_eval.py --corpus /path/corpus.jsonl
  python bench/retrieval_eval.py --corpus ... --rerank cross-encoder/ms-marco-MiniLM-L-6-v2
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import types
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.db.supabase import search_chunks  # noqa: E402
from app.services import law_map  # noqa: E402
from app.services.embedder import get_query_embedding_ex  # noqa: E402
from app.services.section_ops import normalise_section  # noqa: E402

K = 5
DEEP = 30          # candidates per list before fusion
RRF_K = 60         # the constant from Cormack et al.; not tuned here

STOP = set("""a an and are as at be been being but by can could did do does for from had has
have how i if in into is it its may might must no not of on or our shall should so than that
the their them then there these they this those to under upon was we were what when where
which while who whom why will with would you your zambia zambian law act section""".split())


def stem(w: str) -> str:
    # Crude suffix stripping, close enough to Postgres's english config for a
    # prototype: "terminated", "termination", "terminating" -> "terminat".
    for suf in ("ations", "ation", "ings", "ing", "ies", "ied", "ed", "es", "s", "ly"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def tokens(text: str) -> list[str]:
    return [stem(t) for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in STOP and len(t) > 1]


class BM25:
    """Okapi BM25 over an inverted index. k1 and b are the textbook defaults."""

    def __init__(self, docs: list[dict], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.lengths = []
        for i, d in enumerate(docs):
            toks = tokens(d["c"])
            self.lengths.append(len(toks))
            for t, n in Counter(toks).items():
                self.postings[t].append((i, n))
        self.avg = sum(self.lengths) / max(len(self.lengths), 1)
        self.N = len(docs)

    def search(self, query: str, top: int = DEEP) -> list[dict]:
        scores: dict[int, float] = defaultdict(float)
        for t in set(tokens(query)):
            plist = self.postings.get(t)
            if not plist:
                continue
            idf = math.log(1 + (self.N - len(plist) + 0.5) / (len(plist) + 0.5))
            for i, tf in plist:
                norm = tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg))
                scores[i] += idf * norm
        best = sorted(scores.items(), key=lambda kv: -kv[1])[:top]
        return [{**self.docs[i], "score": s} for i, s in best]


def as_row(c: dict) -> dict:
    """RPC rows and local rows into one shape."""
    if "c" in c:
        return {"id": c["id"], "document_id": c["d"], "content": c["c"], "act": c.get("act") or "",
                "section": c.get("s")}
    m = c.get("metadata") or {}
    return {"id": c["id"], "document_id": c["document_id"], "content": c.get("content") or "",
            "act": m.get("act_name") or "", "section": m.get("section_number")}


def demote_repealed(rows: list[dict], k: int = K) -> list[dict]:
    """Production's rule: live law first, at most two matches from a repealed Act."""
    live = [r for r in rows if not law_map.is_repealed(r["document_id"])]
    dead = [r for r in rows if law_map.is_repealed(r["document_id"])]
    keep = min(len(dead), 2 if live else k)
    out = live[: k - keep] + dead[:keep]
    return out + dead[keep: keep + k - len(out)]


def rrf(*lists: list[dict], k: int = RRF_K) -> list[dict]:
    score: dict[str, float] = defaultdict(float)
    row: dict[str, dict] = {}
    for lst in lists:
        for rank, r in enumerate(lst, 1):
            score[r["id"]] += 1.0 / (k + rank)
            row.setdefault(r["id"], r)
    return [row[i] for i, _ in sorted(score.items(), key=lambda kv: -kv[1])]


def norm_act(s: str) -> str:
    s = re.sub(r"\[[^\]]*\]|\(.*?\)|,?\s*(?:19|20)\d{2}\b", " ", (s or "").lower())
    s = re.sub(r"^\s*(?:republic of zambia\s+)?(?:the\s+)?", "", s)
    return re.sub(r"[^a-z]+", " ", s).strip()


def score(q: dict, top: list[dict]) -> dict:
    want_act = norm_act(q["expected_act"])
    want_secs = {normalise_section(s) for s in q.get("expected_sections") or []}

    def from_act(r):
        a = norm_act(r["act"])
        return bool(a) and "amendment" not in a and (want_act in a or a in want_act)

    hits = [from_act(r) for r in top]
    sec_hits = [h and normalise_section(r["section"]) in want_secs for h, r in zip(hits, top)]
    text = " ".join(r["content"] for r in top).lower()
    kws = q.get("expected_keywords") or []
    first = next((i + 1 for i, s in enumerate(sec_hits) if s), None)
    return {
        "act": any(hits),
        "sec": any(sec_hits),
        "p": sum(hits) / K,
        "mrr": 1 / first if first else 0.0,
        "terms": (sum(1 for k in kws if k.lower() in text) / len(kws)) if kws else None,
    }


class patch_settings:
    """Point tools.get_settings at one Settings object for the duration."""

    def __init__(self, module, settings):
        self.module, self.settings = module, settings

    def __enter__(self):
        self.saved = self.module.get_settings
        self.module.get_settings = lambda: self.settings

    def __exit__(self, *exc):
        self.module.get_settings = self.saved


def stale_expectation(expected_act: str) -> str | None:
    """The replacing Act's name if every library Act of the expected name is repealed.

    The gold set was written against the Mines and Minerals Development Act
    2015, which section 97(1) of the Minerals Regulation Commission Act 2024
    repealed. Scored as written, those questions reward a retriever for
    surfacing dead law and penalise one that demotes it. So a question whose
    expected Act is dead is reported apart, not averaged in.
    """
    want = norm_act(expected_act)
    matches = [e for e in law_map._entries().values()
               if norm_act(e.get("title") or "") == want and e.get("status") in ("repealed", "in force", "repeal pending")]
    if matches and all(e.get("status") == "repealed" for e in matches):
        by = [law_map.ref_name(r) for e in matches for r in e.get("repealed_by") or [] if r.get("title")]
        return by[0] if by else "a later Act"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, help="local chunk copy, for the BM25 prototype")
    ap.add_argument("--lexical", choices=["bm25", "pg"], default="bm25")
    ap.add_argument("--rerank", help="cross-encoder model name, e.g. cross-encoder/ms-marco-MiniLM-L-6-v2")
    ap.add_argument("--dump-candidates", type=Path,
                    help="write each question's fused shortlist, for reranking in another environment")
    ap.add_argument("--rerank-order", type=Path,
                    help="score a precomputed rerank: {question id: [chunk ids, best first]}")
    ap.add_argument("--prod", action="store_true",
                    help="also run the real _search_corpus with hybrid off and on (needs the migration)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    gold = [q for q in json.loads((ROOT / "backend" / "tests" / "gold_qa.json").read_text())
            if q.get("expected_act")]
    stale = {q["id"]: stale_expectation(q["expected_act"]) for q in gold}
    stale = {k: v for k, v in stale.items() if v}
    print(f"questions with a known answer: {len(gold)}; expecting a repealed Act: {len(stale)}", flush=True)
    for qid, by in stale.items():
        exp = next(q["expected_act"] for q in gold if q["id"] == qid)
        print(f"    {qid}: expects the {exp}, repealed by the {by}", flush=True)

    bm25 = None
    if args.lexical == "bm25":
        if not args.corpus:
            ap.error("--corpus is required for the bm25 prototype")
        t0 = time.time()
        docs = [json.loads(line) for line in args.corpus.open()]
        bm25 = BM25(docs)
        print(f"BM25 index over {len(docs)} chunks built in {time.time() - t0:.0f}s", flush=True)
    else:
        from app.db.supabase import get_db
        pg = get_db()

    ce = None
    if args.rerank:
        from sentence_transformers import CrossEncoder
        ce = CrossEncoder(args.rerank, max_length=512)

    order = json.loads(args.rerank_order.read_text()) if args.rerank_order else None
    dump: dict[str, dict] = {}
    variants = ["dense", "lexical", "hybrid"] + (["rerank"] if (ce or order) else [])
    if args.prod:
        import asyncio
        from app import config
        from app.services import tools
        base = config.get_settings()
        variants += ["prod-off", "prod-on"]

        def run_prod(question: str, on: bool) -> list[dict]:
            s = base.model_copy(update={"hybrid_retrieval_enabled": on})
            with patch_settings(tools, s):
                out = asyncio.run(tools._search_corpus(question, top_k=K))
            return [{"id": m["chunk_id"], "document_id": m["document_id"], "content": m["content"],
                     "act": m["act_name"], "section": m["section"]} for m in out["result"]["matches"]]
    results: dict[str, list[dict]] = {v: [] for v in variants}
    timing: dict[str, list[float]] = {v: [] for v in variants}
    per_q = []
    for i, q in enumerate(gold, 1):
        emb = get_query_embedding_ex(q["question"])
        t0 = time.time()
        # The production path: threshold 0.6, top_k * 3 over-fetch.
        prod = [as_row(c) for c in search_chunks(emb["vector"], top_k=K * 3, threshold=0.6, space=emb["space"])]
        timing["dense"].append(time.time() - t0)
        dense_top = demote_repealed(prod)[:K]
        # Candidates for fusion come from a deeper, looser dense list.
        deep = [as_row(c) for c in search_chunks(emb["vector"], top_k=DEEP, threshold=0.3, space=emb["space"])]

        t0 = time.time()
        if bm25:
            lex = [as_row(c) for c in bm25.search(q["question"])]
        else:
            lex = [as_row(c) for c in (pg.rpc("search_legal_chunks_keyword", {
                "query_text": q["question"], "match_count": DEEP,
                "caller_user_id": None, "attached_doc_ids": []}).execute().data or [])]
        timing["lexical"].append(time.time() - t0)
        lex_top = demote_repealed(lex)[:K]

        fused = rrf(deep, lex)
        hyb_top = demote_repealed(fused)[:K]

        row = {"id": q["id"], "difficulty": q.get("difficulty")}
        for name, top in (("dense", dense_top), ("lexical", lex_top), ("hybrid", hyb_top)):
            s = score(q, top)
            results[name].append(s)
            row[name] = s
        short = fused[:DEEP]
        if args.dump_candidates:
            dump[q["id"]] = {"question": q["question"],
                             "candidates": [{"id": r["id"], "content": r["content"][:2000]} for r in short]}
        if ce or order:
            t0 = time.time()
            if ce:
                scores = ce.predict([(q["question"], r["content"][:2000]) for r in short])
                ranked = [r for _, r in sorted(zip(scores, short), key=lambda x: -x[0])]
            else:
                pos = {cid: i for i, cid in enumerate(order.get(q["id"], []))}
                ranked = sorted(short, key=lambda r: pos.get(r["id"], len(pos)))
            timing["rerank"].append(time.time() - t0)
            s = score(q, demote_repealed(ranked)[:K])
            results["rerank"].append(s)
            row["rerank"] = s
        if args.prod:
            for name, on in (("prod-off", False), ("prod-on", True)):
                t0 = time.time()
                top = run_prod(q["question"], on)
                timing[name].append(time.time() - t0)
                s = score(q, top)
                results[name].append(s)
                row[name] = s
        per_q.append(row)
        print(f"  [{i:>2}/{len(gold)}] {q['id']:<12} " + "  ".join(
            f"{v}:{'S' if row[v]['sec'] else ('A' if row[v]['act'] else '-')}" for v in variants), flush=True)

    if args.dump_candidates:
        args.dump_candidates.write_text(json.dumps(dump))
        print(f"wrote {len(dump)} shortlists to {args.dump_candidates}")
    current_ids = {q["id"] for q in gold if q["id"] not in stale}

    def mean(v, key, ids):
        xs = [r[key] for r, q in zip(results[v], gold) if q["id"] in ids and r[key] is not None]
        return sum(xs) / len(xs) if xs else 0.0

    summary = {}
    for label, ids in (("current law", current_ids), ("all, as written", {q["id"] for q in gold})):
        print(f"\n{label} ({len(ids)} questions)")
        print(f"{'variant':<9} {'act@5':>6} {'sec@5':>6} {'p@5':>6} {'mrr':>6} {'terms':>6} {'ms/q':>7}")
        for v in variants:
            s = {k: round(mean(v, k, ids), 3) for k in ("act", "sec", "p", "mrr", "terms")}
            ms = 1000 * sum(timing[v]) / max(len(timing[v]), 1)
            s["ms"] = round(ms)
            summary.setdefault(label, {})[v] = s
            print(f"{v:<9} {s['act']:>6.0%} {s['sec']:>6.0%} {s['p']:>6.0%} {s['mrr']:>6.2f} {s['terms']:>6.0%} {ms:>7.0f}")
    print("  (A = right Act in the top five, S = right section too, - = neither)")
    if args.out:
        args.out.write_text(json.dumps({"summary": summary, "per_question": per_q,
                                        "lexical": args.lexical, "rerank": args.rerank}, indent=1))
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
