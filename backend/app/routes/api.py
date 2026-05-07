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
from ..services.agent import run_agent
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
    web_search: bool = False
    history: list[dict] | None = None


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
async def chat_stream(request: ChatRequest):
    """
    Agentic RAG pipeline. Server-Sent Events.

    Drives the model through a tool-use loop with `search_corpus` always
    available and Tavily-backed web tools added when `web_search=True`.

    Event types streamed (each as `data: {json}\n\n`):
      thinking, tool_call, tool_result, token, sources, done, error.

    Backwards-compat: `token` and `sources` events keep the same shape the
    pre-agent client already understands; new clients can additionally render
    `tool_call`/`tool_result`.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    async def event_stream():
        async for event in run_agent(
            user_query=request.query,
            model=request.model,
            web_enabled=bool(request.web_search),
            history=request.history,
        ):
            # The pre-agent client expects `chunks_used` on the sources event.
            if event.get("type") == "sources":
                payload = {
                    "type": "sources",
                    "db": event.get("db", []),
                    "web": event.get("web", []),
                    # Legacy field — first 8 db sources mapped to old shape
                    "chunks_used": [
                        {
                            "id": s.get("id"),
                            "act_name": s.get("act_name"),
                            "section": s.get("section"),
                            "part": s.get("part"),
                            "page_start": s.get("page_start"),
                            "page_end": s.get("page_end"),
                            "similarity": s.get("similarity"),
                            "content_preview": s.get("content_preview"),
                        }
                        for s in event.get("db", [])[:8]
                    ],
                }
                yield f"data: {json.dumps(payload)}\n\n"
            else:
                yield f"data: {json.dumps(event)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/documents/{document_id}/pdf")
def get_document_pdf_url(document_id: str, expires_in: int = 3600):
    """
    Return a short-lived signed URL for the canonical PDF of a legal document.

    The PDF lives in the private `legal-docs` Supabase Storage bucket; we mint
    a signed URL on demand so the client (PDF.js viewer) can fetch it.
    """
    from ..db.supabase import get_db

    db = get_db()
    res = (
        db.table("legal_documents")
        .select("id, title, short_name, pdf_storage_path, pdf_page_count, canonical_url")
        .eq("id", document_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="document not found")
    row = res.data[0]
    storage_path = row.get("pdf_storage_path")
    if not storage_path:
        raise HTTPException(status_code=404, detail="no PDF stored for this document")

    # storage_path is "legal-docs/<file>"; the storage SDK takes bucket + key
    bucket, _, key = storage_path.partition("/")
    try:
        signed = db.storage.from_(bucket).create_signed_url(key, expires_in)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"signed-url failed: {e}")

    return {
        "document_id": row["id"],
        "title": row.get("title"),
        "short_name": row.get("short_name"),
        "page_count": row.get("pdf_page_count"),
        "canonical_url": row.get("canonical_url"),
        "signed_url": signed.get("signedURL") or signed.get("signed_url") or signed.get("signedUrl"),
        "expires_in": expires_in,
    }


@router.get("/documents/by-title")
def get_document_by_title(title: str):
    """
    Look up a document by exact or fuzzy title match — used by the chat UI when
    a citation snapshot only knows the act name (not the document_id).
    """
    from ..db.supabase import get_db

    db = get_db()
    # Exact match first
    res = (
        db.table("legal_documents")
        .select("id, title, short_name, pdf_storage_path, pdf_page_count")
        .eq("title", title)
        .limit(1)
        .execute()
    )
    if not res.data:
        # Fall back to ILIKE so 'REPUBLIC OF ZAMBIA THE COMPANIES ACT' still
        # resolves to the new 'Companies Act, No. 10 of 2017' row.
        res = (
            db.table("legal_documents")
            .select("id, title, short_name, pdf_storage_path, pdf_page_count")
            .ilike("title", f"%{title.split()[-2] if len(title.split()) > 1 else title}%")
            .limit(5)
            .execute()
        )
    if not res.data:
        raise HTTPException(status_code=404, detail="no document matched")
    return {"matches": res.data}


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
