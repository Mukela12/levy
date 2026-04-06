"""
API Routes — FastAPI endpoints for Levy.

Three endpoints for the baseline RAG system:
  POST /api/chat       — Full RAG: retrieve + generate answer with citations
  POST /api/search     — Retrieval only: test what chunks come back (no LLM)
  GET  /api/documents  — List ingested documents and stats
"""

import os
import tempfile
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import time
from ..services import rag
from ..services.ingester import ingest_pdf
from ..services.embedder import get_query_embedding
from ..db.supabase import search_chunks
from ..prompts.legal_qa import SYSTEM_PROMPT, build_context_prompt
from ..prompts.irac_brief import IRAC_SYSTEM_PROMPT, build_irac_prompt
from ..providers.anthropic_provider import generate_response, generate_response_stream
from ..models.schemas import BriefRequest
from ..config import get_settings

router = APIRouter(prefix="/api")


# --- Request/Response Models ---

class ChatRequest(BaseModel):
    query: str
    model: str | None = None
    top_k: int | None = None
    threshold: float | None = None


class SearchRequest(BaseModel):
    query: str
    top_k: int | None = None
    threshold: float | None = None


# --- Endpoints ---

@router.post("/chat")
def chat(request: ChatRequest):
    """
    Full RAG pipeline: embed query → search → generate answer with citations.

    This is the main endpoint users interact with.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        result = rag.query(
            question=request.query,
            model=request.model,
            top_k=request.top_k,
            threshold=request.threshold,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
def search(request: SearchRequest):
    """
    Retrieval only — returns matching chunks without LLM generation.

    Use this endpoint to:
    - Test retrieval quality independently
    - Debug which chunks match a query
    - Evaluate Recall@K and Precision@K
    - Save LLM costs during development
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        result = rag.search_only(
            question=request.query,
            top_k=request.top_k,
            threshold=request.threshold,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
def chat_stream(request: ChatRequest):
    """
    Streaming RAG pipeline — returns answer tokens via Server-Sent Events.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    settings = get_settings()
    top_k = request.top_k or settings.retrieval_top_k
    threshold = request.threshold or settings.similarity_threshold

    def event_stream():
        timing = {}

        t0 = time.time()
        query_embedding = get_query_embedding(request.query)
        timing["embedding_ms"] = round((time.time() - t0) * 1000)

        t0 = time.time()
        chunks = search_chunks(query_embedding, top_k=top_k, threshold=threshold)
        timing["retrieval_ms"] = round((time.time() - t0) * 1000)

        user_message = build_context_prompt(request.query, chunks)

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

        yield f"data: {json.dumps({'type': 'sources', 'chunks_used': chunks_used})}\n\n"

        t0 = time.time()
        for text_chunk in generate_response_stream(
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
            model=request.model,
        ):
            yield f"data: {json.dumps({'type': 'token', 'content': text_chunk})}\n\n"

        timing["generation_ms"] = round((time.time() - t0) * 1000)
        timing["total_ms"] = timing["embedding_ms"] + timing["retrieval_ms"] + timing["generation_ms"]

        yield f"data: {json.dumps({'type': 'done', 'timing': timing, 'chunks_used': chunks_used})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/documents")
def list_documents():
    """List all ingested documents and their stats."""
    try:
        return rag.get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload and ingest a PDF document."""
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Run ingestion pipeline
        result = ingest_pdf(tmp_path)

        # Clean up
        os.unlink(tmp_path)

        return {
            "status": result.get("status", "unknown"),
            "document_id": result.get("document", {}).get("id"),
            "chunks_created": result.get("chunks_created", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/brief/generate")
def generate_brief(request: BriefRequest):
    """
    Generate an IRAC legal brief from conversation history.

    Takes a list of conversation messages and produces a structured
    Issue, Rule, Application, Conclusion analysis based on the
    legal topics discussed.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages cannot be empty")

    try:
        user_message = build_irac_prompt(request.messages)

        result = generate_response(
            system_prompt=IRAC_SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=4096,
        )

        # Parse JSON from response
        answer = result["answer"]

        # Handle case where Claude wraps JSON in markdown code blocks
        if "```json" in answer:
            answer = answer.split("```json")[1].split("```")[0].strip()
        elif "```" in answer:
            answer = answer.split("```")[1].split("```")[0].strip()

        brief_data = json.loads(answer)
        return {
            "issue": brief_data.get("issue", ""),
            "rule": brief_data.get("rule", ""),
            "application": brief_data.get("application", ""),
            "conclusion": brief_data.get("conclusion", ""),
            "citations": brief_data.get("citations", []),
        }
    except json.JSONDecodeError:
        # If JSON parsing fails, return the raw text in the issue field
        return {
            "issue": answer,
            "rule": "",
            "application": "",
            "conclusion": "",
            "citations": [],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
