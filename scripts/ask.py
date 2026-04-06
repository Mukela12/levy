#!/usr/bin/env python3
"""
Levy CLI — Ask legal questions from the terminal.

Usage:
  python scripts/ask.py "What are the penalties for mining without a license?"
  python scripts/ask.py --search-only "maternity leave in Zambia"
  python scripts/ask.py                    # interactive mode
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.rag import query, search_only, get_stats


def print_answer(result: dict):
    print(f"\n{'='*70}")
    print(f"  LEVY — Zambian Legal AI")
    print(f"{'='*70}\n")
    print(result["answer"])
    print(f"\n{'─'*70}")
    print(f"  Sources ({result['chunks_retrieved']} chunks):")
    for c in result["chunks_used"]:
        print(f"    - {c['act_name']} S.{c['section']} (sim: {c['similarity']:.2f})")
    print(f"  Model: {result['model']}")
    print(f"  Timing: embed {result['timing']['embedding_ms']}ms | "
          f"retrieve {result['timing']['retrieval_ms']}ms | "
          f"generate {result['timing']['generation_ms']}ms | "
          f"total {result['timing']['total_ms']}ms")
    print(f"  Tokens: {result['usage']['input_tokens']} in / {result['usage']['output_tokens']} out")
    print(f"{'='*70}\n")


def print_search(result: dict):
    print(f"\n{'='*70}")
    print(f"  RETRIEVAL RESULTS ({result['total']} chunks)")
    print(f"{'='*70}\n")
    for i, r in enumerate(result["results"], 1):
        print(f"  [{i}] {r['act_name']} — Section {r['section']} (sim: {r['similarity']:.4f})")
        preview = r["content"][:150].replace("\n", " ")
        print(f"      {preview}...")
        print()
    print(f"  Timing: {result['timing']['total_ms']}ms")
    print(f"{'='*70}\n")


def interactive_mode():
    stats = get_stats()
    print(f"\n  LEVY — Zambian Legal AI (Interactive Mode)")
    print(f"  {stats['documents']} Acts loaded, {sum(d['total_chunks'] for d in stats['details'])} chunks")
    print(f"  Type 'quit' to exit, prefix with /search for retrieval-only\n")

    while True:
        try:
            q = input("  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye!")
            break

        if not q or q.lower() in ("quit", "exit", "q"):
            print("  Goodbye!")
            break

        if q.startswith("/search "):
            q = q[8:]
            result = search_only(q, top_k=5, threshold=0.3)
            print_search(result)
        else:
            result = query(q, top_k=5, threshold=0.3)
            print_answer(result)


if __name__ == "__main__":
    search_mode = "--search-only" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if args:
        question = " ".join(args)
        if search_mode:
            result = search_only(question, top_k=5, threshold=0.3)
            print_search(result)
        else:
            result = query(question, top_k=5, threshold=0.3)
            print_answer(result)
    else:
        interactive_mode()
