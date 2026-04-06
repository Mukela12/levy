"""
RAG Service — The core retrieval-augmented generation pipeline.

This is the brain of Levy. It orchestrates the full flow:
    User Question → Embed → Search → Build Prompt → LLM → Answer + Citations

This implements Chapter 3 of the Twig RAG guide: the Baseline RAG Pipeline.
"""

import time
from ..services.embedder import get_query_embedding
from ..db.supabase import search_chunks, get_document_stats
from ..prompts.legal_qa import SYSTEM_PROMPT, build_context_prompt
from ..providers.anthropic_provider import generate_response
from ..config import get_settings


def query(
    question: str,
    model: str | None = None,
    top_k: int | None = None,
    threshold: float | None = None,
) -> dict:
    """
    Execute the full RAG pipeline for a legal question.

    Steps:
    1. Embed the user's question into a 3072-dim vector
    2. Search Supabase for the most similar legal chunks
    3. Build a context-enriched prompt with the retrieved chunks
    4. Send to Claude for answer generation
    5. Return the answer with citations and diagnostics

    Returns a dict with: answer, citations, chunks_used, model, usage, timing
    """
    settings = get_settings()
    top_k = top_k or settings.retrieval_top_k
    threshold = threshold or settings.similarity_threshold

    timing = {}

    # Step 1: Embed the query
    t0 = time.time()
    query_embedding = get_query_embedding(question)
    timing["embedding_ms"] = round((time.time() - t0) * 1000)

    # Step 2: Retrieve relevant chunks from Supabase
    t0 = time.time()
    chunks = search_chunks(query_embedding, top_k=top_k, threshold=threshold)
    timing["retrieval_ms"] = round((time.time() - t0) * 1000)

    # Step 3: Build the context-enriched prompt
    user_message = build_context_prompt(question, chunks)

    # Step 4: Generate answer with Claude
    t0 = time.time()
    llm_result = generate_response(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        model=model,
    )
    timing["generation_ms"] = round((time.time() - t0) * 1000)
    timing["total_ms"] = timing["embedding_ms"] + timing["retrieval_ms"] + timing["generation_ms"]

    # Step 5: Format the response with chunk metadata for transparency
    chunks_used = []
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        chunks_used.append({
            "id": chunk.get("id"),
            "act_name": metadata.get("act_name", "Unknown"),
            "section": metadata.get("section_number", ""),
            "part": metadata.get("part_number", ""),
            "page_start": chunk.get("page_start"),
            "page_end": chunk.get("page_end"),
            "similarity": round(chunk.get("similarity", 0), 4),
            "content_preview": chunk.get("content", "")[:200] + "...",
        })

    return {
        "answer": llm_result["answer"],
        "chunks_used": chunks_used,
        "chunks_retrieved": len(chunks),
        "model": llm_result["model"],
        "usage": llm_result["usage"],
        "timing": timing,
    }


def search_only(
    question: str,
    top_k: int | None = None,
    threshold: float | None = None,
) -> dict:
    """
    Search without generation — useful for testing retrieval quality.

    Returns just the retrieved chunks and their metadata, without
    sending anything to the LLM. This is essential for evaluating
    the retriever independently (Chapter 14 of the Twig guide:
    Evaluation Metrics — Retriever layer).
    """
    settings = get_settings()
    top_k = top_k or settings.retrieval_top_k
    threshold = threshold or settings.similarity_threshold

    t0 = time.time()
    query_embedding = get_query_embedding(question)
    embedding_ms = round((time.time() - t0) * 1000)

    t0 = time.time()
    chunks = search_chunks(query_embedding, top_k=top_k, threshold=threshold)
    retrieval_ms = round((time.time() - t0) * 1000)

    results = []
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        results.append({
            "id": chunk.get("id"),
            "content": chunk.get("content", ""),
            "act_name": metadata.get("act_name", "Unknown"),
            "section": metadata.get("section_number", ""),
            "part": metadata.get("part_number", ""),
            "page_start": chunk.get("page_start"),
            "page_end": chunk.get("page_end"),
            "similarity": round(chunk.get("similarity", 0), 4),
        })

    return {
        "results": results,
        "total": len(results),
        "timing": {
            "embedding_ms": embedding_ms,
            "retrieval_ms": retrieval_ms,
            "total_ms": embedding_ms + retrieval_ms,
        },
    }


def get_stats() -> dict:
    """Get statistics about ingested documents."""
    docs = get_document_stats()
    return {
        "documents": len(docs),
        "details": [
            {
                "title": d.get("title", "Unknown"),
                "year": d.get("year"),
                "total_chunks": d.get("total_chunks", 0),
                "total_sections": d.get("total_sections", 0),
            }
            for d in docs
        ],
    }
