"""Fuse vector and keyword results into one ranking.

Vector search finds meaning ("lunch break" reaches "meal break"). Keyword
search finds the words the statute actually uses, and on the gold questions
whose expected Act is in force it found the right Act far more often than
vectors did: the vectors kept preferring the repealed predecessor Acts, whose
wording is almost the same as their replacements'. Fused, the right section
reached the top five in 31% of those questions against 19% for vectors alone
(bench/retrieval_eval.py, 28 September 2026).

Reciprocal rank fusion combines positions, not scores, so a BM25-style score
of 12 and a cosine of 0.8 never have to be compared. A chunk ranked well by
both rises; one found by only one method can still survive.

Two cross-encoder rerankers were tried on the fused shortlist and made it
worse (MiniLM: right Act in the top five 38% against hybrid's 69%;
bge-reranker-base: 56%, at 1.6 s per search on CPU). Neither knows that a
repealed Act and its replacement are different law, so both put the dead one
back on top. There is no reranker here on purpose.
"""
from __future__ import annotations

from collections import defaultdict

# The constant from Cormack, Clarke and Buettcher (2009). Not tuned on the
# gold set: 16 questions are too few to tune anything on.
RRF_K = 60


def rrf(*lists: list[dict], k: int = RRF_K, key: str = "id") -> list[dict]:
    """Rows from every list, best fused rank first. The first copy of a row wins."""
    score: dict[str, float] = defaultdict(float)
    first: dict[str, dict] = {}
    for rows in lists:
        for rank, row in enumerate(rows, 1):
            rid = row.get(key)
            if rid is None:
                continue
            score[rid] += 1.0 / (k + rank)
            first.setdefault(rid, row)
    return [first[rid] for rid, _ in sorted(score.items(), key=lambda kv: (-kv[1], str(kv[0])))]


def fuse(dense: list[dict], keyword: list[dict]) -> list[dict]:
    """Dense and keyword candidates as one list, each row carrying a similarity.

    A keyword-only row takes its cosine from the keyword search itself, which
    computes it against the same query vector, so every row has the score the
    interface and the library-miss check expect.
    """
    fused = rrf(dense, keyword)
    for row in fused:
        if row.get("similarity") is None:
            row["similarity"] = 0.0
    return fused
