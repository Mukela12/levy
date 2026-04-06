"""
Levy Assessment Framework — Measures retrieval and generation quality.

This implements Chapter 14 of the Twig RAG guide: Assessment Metrics.
We measure at two layers:

LAYER 1 - RETRIEVAL METRICS (no LLM needed):
  - Act Match Rate: Did we retrieve chunks from the correct Act?
  - Keyword Hit Rate: Do retrieved chunks contain expected terms?

LAYER 2 - GENERATION METRICS (requires LLM):
  - Groundedness: Does the answer cite retrieved evidence?
  - Refusal on negatives: Does the system correctly say "I don't know"?

Usage:
  python tests/assess.py                    # retrieval-only (fast, free)
  python tests/assess.py --full             # retrieval + generation (uses LLM)
  python tests/assess.py --question "env-01" # test a single question
"""

import json
import sys
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.services.rag import search_only, query


def load_gold_set() -> list[dict]:
    """Load the gold Q&A set."""
    gold_path = Path(__file__).parent / "gold_qa.json"
    with open(gold_path) as f:
        return json.load(f)


def assess_retrieval(test_case: dict) -> dict:
    """
    Assess retrieval quality for a single test case.

    Metrics:
    - act_match: Did at least one chunk come from the expected Act?
    - keyword_hits: How many expected keywords appear in retrieved text?
    - keyword_rate: keyword_hits / total_expected_keywords
    """
    question = test_case["question"]
    expected_act = test_case.get("expected_act")
    expected_keywords = test_case.get("expected_keywords", [])

    result = search_only(question, top_k=5, threshold=0.3)
    chunks = result["results"]

    # Act Match: check if ANY retrieved chunk is from the expected act
    act_match = False
    if expected_act:
        for chunk in chunks:
            chunk_act = chunk.get("act_name", "")
            ea = expected_act.lower()
            ca = chunk_act.lower()
            # Bidirectional: either can contain the other
            if ea in ca or ca in ea:
                act_match = True
                break

    # Keyword Hits: check how many expected keywords appear in retrieved text
    all_text = " ".join(c.get("content", "") for c in chunks).lower()
    keyword_hits = sum(1 for kw in expected_keywords if kw.lower() in all_text)
    keyword_rate = keyword_hits / len(expected_keywords) if expected_keywords else 1.0

    # Top similarity score
    top_sim = chunks[0]["similarity"] if chunks else 0.0

    return {
        "id": test_case["id"],
        "question": question[:80],
        "difficulty": test_case.get("difficulty", "?"),
        "chunks_retrieved": len(chunks),
        "act_match": act_match,
        "keyword_hits": keyword_hits,
        "keyword_total": len(expected_keywords),
        "keyword_rate": round(keyword_rate, 2),
        "top_similarity": round(top_sim, 4),
        "timing_ms": result["timing"]["total_ms"],
    }


def assess_generation(test_case: dict) -> dict:
    """
    Assess full RAG generation for a single test case.

    Metrics:
    - has_citations: Does the answer contain section references?
    - mentions_act: Does the answer name the correct Act?
    - is_negative_correct: For negative tests, does it say "I don't know"?
    """
    question = test_case["question"]
    expected_act = test_case.get("expected_act")
    is_negative = test_case.get("difficulty") == "negative"

    result = query(question, top_k=5, threshold=0.3)
    answer = result["answer"].lower()

    # Check for citations (section references)
    has_citations = any(
        marker in answer
        for marker in ["section", "sect.", "s.", "part "]
    )

    # Check if answer mentions the correct act
    mentions_act = False
    if expected_act:
        mentions_act = expected_act.lower() in answer

    # For negative tests: system should say it can't answer
    is_negative_correct = None
    if is_negative:
        refusal_markers = [
            "not contain", "cannot answer", "don't have", "no relevant",
            "outside the scope", "not available", "unable to find",
            "do not have", "not in", "beyond"
        ]
        is_negative_correct = any(m in answer for m in refusal_markers)

    return {
        "id": test_case["id"],
        "has_citations": has_citations,
        "mentions_act": mentions_act,
        "is_negative_correct": is_negative_correct,
        "answer_length": len(result["answer"]),
        "model": result["model"],
        "tokens_in": result["usage"]["input_tokens"],
        "tokens_out": result["usage"]["output_tokens"],
        "timing_ms": result["timing"]["total_ms"],
    }


def run_assessment(full: bool = False, question_id: str = None):
    """Run the assessment suite and print results."""
    gold_set = load_gold_set()

    if question_id:
        gold_set = [t for t in gold_set if t["id"] == question_id]
        if not gold_set:
            print(f"No test case found with ID: {question_id}")
            return

    print(f"\n{'='*70}")
    print(f"  LEVY ASSESSMENT — {'Full (Retrieval + Generation)' if full else 'Retrieval Only'}")
    print(f"  Test cases: {len(gold_set)}")
    print(f"{'='*70}\n")

    # --- Retrieval Assessment ---
    print("LAYER 1: RETRIEVAL METRICS")
    print("-" * 70)
    print(f"{'ID':<10} {'Difficulty':<10} {'Act?':<6} {'KW Rate':<8} {'TopSim':<8} {'ms':<6}")
    print("-" * 70)

    retrieval_results = []
    for test in gold_set:
        result = assess_retrieval(test)
        retrieval_results.append(result)
        act_mark = "Y" if result["act_match"] else "N"
        print(
            f"{result['id']:<10} "
            f"{result['difficulty']:<10} "
            f"{act_mark:<6} "
            f"{result['keyword_rate']:<8.0%} "
            f"{result['top_similarity']:<8.4f} "
            f"{result['timing_ms']:<6}"
        )

    # Aggregate retrieval metrics
    total = len(retrieval_results)
    positive_results = [r for r in retrieval_results if r["difficulty"] != "negative"]
    act_match_rate = sum(1 for r in positive_results if r["act_match"]) / len(positive_results) if positive_results else 0
    avg_keyword_rate = sum(r["keyword_rate"] for r in positive_results) / len(positive_results) if positive_results else 0
    avg_similarity = sum(r["top_similarity"] for r in retrieval_results) / total if total else 0
    avg_time = sum(r["timing_ms"] for r in retrieval_results) / total if total else 0

    print(f"\n{'='*70}")
    print(f"  RETRIEVAL SUMMARY")
    print(f"  Act Match Rate:     {act_match_rate:.0%} ({sum(1 for r in positive_results if r['act_match'])}/{len(positive_results)})")
    print(f"  Avg Keyword Rate:   {avg_keyword_rate:.0%}")
    print(f"  Avg Top Similarity: {avg_similarity:.4f}")
    print(f"  Avg Latency:        {avg_time:.0f}ms")
    print(f"{'='*70}\n")

    # --- Generation Assessment ---
    if full:
        print("\nLAYER 2: GENERATION METRICS")
        print("-" * 70)
        print(f"{'ID':<10} {'Citations?':<12} {'Act?':<6} {'Neg?':<6} {'Tokens':<10} {'ms':<6}")
        print("-" * 70)

        gen_results = []
        total_cost_tokens = 0
        for test in gold_set:
            result = assess_generation(test)
            gen_results.append(result)
            total_cost_tokens += result["tokens_in"] + result["tokens_out"]

            cite_mark = "Y" if result["has_citations"] else "N"
            act_mark = "Y" if result["mentions_act"] else "N"
            neg_mark = "-"
            if result["is_negative_correct"] is not None:
                neg_mark = "Y" if result["is_negative_correct"] else "N"

            tokens = f"{result['tokens_in']}+{result['tokens_out']}"
            print(
                f"{result['id']:<10} "
                f"{cite_mark:<12} "
                f"{act_mark:<6} "
                f"{neg_mark:<6} "
                f"{tokens:<10} "
                f"{result['timing_ms']:<6}"
            )

        positive_gen = [r for r in gen_results if r["is_negative_correct"] is None]
        citation_rate = sum(1 for r in positive_gen if r["has_citations"]) / len(positive_gen) if positive_gen else 0
        act_mention_rate = sum(1 for r in positive_gen if r["mentions_act"]) / len(positive_gen) if positive_gen else 0
        avg_gen_time = sum(r["timing_ms"] for r in gen_results) / len(gen_results) if gen_results else 0

        print(f"\n{'='*70}")
        print(f"  GENERATION SUMMARY")
        print(f"  Citation Rate:      {citation_rate:.0%}")
        print(f"  Act Mention Rate:   {act_mention_rate:.0%}")
        print(f"  Total Tokens:       {total_cost_tokens:,}")
        print(f"  Avg Latency:        {avg_gen_time:.0f}ms")
        print(f"{'='*70}\n")

    # Save results
    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "full" if full else "retrieval_only",
        "retrieval": {
            "act_match_rate": round(act_match_rate, 4),
            "avg_keyword_rate": round(avg_keyword_rate, 4),
            "avg_top_similarity": round(avg_similarity, 4),
            "avg_latency_ms": round(avg_time),
            "details": retrieval_results,
        },
    }
    if full:
        output["generation"] = {
            "citation_rate": round(citation_rate, 4),
            "act_mention_rate": round(act_mention_rate, 4),
            "total_tokens": total_cost_tokens,
            "details": gen_results,
        }

    results_path = Path(__file__).parent / "assessment_results.json"
    with open(results_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Results saved to: {results_path}")


if __name__ == "__main__":
    full_mode = "--full" in sys.argv
    question_id = None
    for i, arg in enumerate(sys.argv):
        if arg == "--question" and i + 1 < len(sys.argv):
            question_id = sys.argv[i + 1]

    run_assessment(full=full_mode, question_id=question_id)
