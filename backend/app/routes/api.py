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
    user_id: str | None = None
    session_id: str | None = None
    attached_doc_ids: list[str] | None = None


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
            owner_id=request.user_id,
            session_id=request.session_id,
            attached_doc_ids=request.attached_doc_ids,
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


@router.get("/artifacts/{artifact_id}/pdf")
def get_artifact_pdf_url(artifact_id: str, expires_in: int = 3600):
    """Signed URL for an agent-generated artifact PDF."""
    from ..db.supabase import get_db

    db = get_db()
    res = (
        db.table("artifacts")
        .select("id, title, kind, storage_path, page_count, size_bytes, source, meta, created_at")
        .eq("id", artifact_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="artifact not found")
    row = res.data[0]
    storage_path = row.get("storage_path")
    if not storage_path or storage_path == "artifacts/pending":
        raise HTTPException(status_code=409, detail="artifact upload not finalized")

    bucket, _, key = storage_path.partition("/")
    try:
        signed = db.storage.from_(bucket).create_signed_url(key, expires_in)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"signed-url failed: {e}")

    return {
        "artifact_id": row["id"],
        "title": row.get("title"),
        "kind": row.get("kind"),
        "page_count": row.get("page_count"),
        "size_bytes": row.get("size_bytes"),
        "source": row.get("source"),
        "meta": row.get("meta"),
        "created_at": row.get("created_at"),
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
def list_documents(
    user_id: str | None = None,
    session_id: str | None = None,
    folder_id: str | None = None,
):
    """
    List documents visible to the caller.

    - `global`   : the curated Zambian-law library (always available)
    - `owned`    : documents this user uploaded; if `folder_id` is given,
                   filtered to that folder. Pass `folder_id="unfiled"` to get
                   the user's documents that are not in any folder.
    - `attached` : documents attached to the active chat session
    """
    from ..db.supabase import get_db

    db = get_db()

    cols = (
        "id, title, short_name, year, document_type, total_chunks, "
        "pdf_page_count, pdf_size_bytes, pdf_storage_path, canonical_url, "
        "is_global, owner_id, folder_id, created_at"
    )

    global_docs = (
        db.table("legal_documents").select(cols).eq("is_global", True)
        .order("title").execute().data or []
    )

    owned: list[dict] = []
    if user_id:
        q = db.table("legal_documents").select(cols).eq("owner_id", user_id)
        if folder_id == "unfiled":
            q = q.is_("folder_id", "null")
        elif folder_id:
            q = q.eq("folder_id", folder_id)
        owned = q.order("created_at", desc=True).execute().data or []

    attached: list[dict] = []
    if session_id:
        ids_res = (
            db.table("chat_session_documents").select("document_id")
            .eq("session_id", session_id).execute()
        )
        ids = [r["document_id"] for r in (ids_res.data or [])]
        if ids:
            attached = (
                db.table("legal_documents").select(cols).in_("id", ids)
                .order("title").execute().data or []
            )

    return {
        "global": global_docs,
        "owned": owned,
        "attached": attached,
        "counts": {
            "global": len(global_docs),
            "owned": len(owned),
            "attached": len(attached),
        },
    }


# ─── Folders (user-created groupings of uploaded documents) ──────────────────


class CreateFolderRequest(BaseModel):
    user_id: str
    name: str


class RenameFolderRequest(BaseModel):
    name: str


class MoveDocumentRequest(BaseModel):
    folder_id: str | None = None  # null = remove from any folder


@router.get("/folders")
def list_folders(user_id: str):
    """Return the user's folders + a per-folder document count."""
    from ..db.supabase import get_db
    db = get_db()
    folders = (
        db.table("document_folders").select("id, name, created_at")
        .eq("owner_id", user_id).order("created_at", desc=False).execute().data or []
    )
    # Count user docs per folder, plus an "unfiled" count for ones with folder_id null.
    docs = (
        db.table("legal_documents").select("id, folder_id").eq("owner_id", user_id)
        .execute().data or []
    )
    counts: dict[str, int] = {}
    unfiled = 0
    for d in docs:
        fid = d.get("folder_id")
        if fid is None:
            unfiled += 1
        else:
            counts[fid] = counts.get(fid, 0) + 1
    return {
        "folders": [
            {**f, "doc_count": counts.get(f["id"], 0)} for f in folders
        ],
        "unfiled_count": unfiled,
    }


@router.post("/folders")
def create_folder(request: CreateFolderRequest):
    from ..db.supabase import get_db
    db = get_db()
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    try:
        row = db.table("document_folders").insert(
            {"owner_id": request.user_id, "name": name}
        ).execute()
    except Exception as e:  # noqa: BLE001
        # Likely unique-name collision
        raise HTTPException(status_code=409, detail=str(e))
    return row.data[0] if row.data else {"status": "ok"}


@router.patch("/folders/{folder_id}")
def rename_folder(folder_id: str, request: RenameFolderRequest):
    from ..db.supabase import get_db
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    db = get_db()
    db.table("document_folders").update(
        {"name": name, "updated_at": "now()"}
    ).eq("id", folder_id).execute()
    return {"status": "ok"}


@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: str, cascade: bool = False):
    """Delete a folder. Documents inside are unfiled (folder_id=null), not removed,
    unless cascade=true (which deletes their chunks + storage too — destructive)."""
    from ..db.supabase import get_db
    db = get_db()
    if cascade:
        # Delete all docs in the folder; chunks cascade via FK; PDFs in storage
        # are NOT auto-cleaned here (leftover storage objects can be swept
        # later in Phase 6 polish).
        db.table("legal_documents").delete().eq("folder_id", folder_id).execute()
    else:
        db.table("legal_documents").update({"folder_id": None}).eq("folder_id", folder_id).execute()
    db.table("document_folders").delete().eq("id", folder_id).execute()
    return {"status": "ok", "cascade": cascade}


@router.patch("/documents/{document_id}/folder")
def move_document_to_folder(document_id: str, request: MoveDocumentRequest):
    """Move a user-owned document into a folder (or clear by sending null)."""
    from ..db.supabase import get_db
    db = get_db()
    db.table("legal_documents").update({"folder_id": request.folder_id}).eq("id", document_id).execute()
    return {"status": "ok", "folder_id": request.folder_id}


# ─── Per-thread document attachment ──────────────────────────────────────────


class AttachDocRequest(BaseModel):
    document_id: str


@router.get("/sessions/{session_id}/documents")
def list_session_documents(session_id: str):
    """Documents currently attached to a chat session."""
    from ..db.supabase import get_db
    db = get_db()
    ids_res = (
        db.table("chat_session_documents").select("document_id, attached_at")
        .eq("session_id", session_id).execute()
    )
    rows = ids_res.data or []
    if not rows:
        return {"documents": []}
    ids = [r["document_id"] for r in rows]
    docs = (
        db.table("legal_documents")
        .select("id, title, short_name, total_chunks, pdf_page_count, owner_id, is_global")
        .in_("id", ids).execute().data or []
    )
    by_id = {d["id"]: d for d in docs}
    return {
        "documents": [
            {**by_id[r["document_id"]], "attached_at": r["attached_at"]}
            for r in rows if r["document_id"] in by_id
        ],
    }


@router.post("/sessions/{session_id}/documents/attach")
def attach_document(session_id: str, request: AttachDocRequest):
    """Attach a document to a chat session so search_corpus can see it."""
    from ..db.supabase import get_db
    db = get_db()
    # Idempotent — primary key is (session_id, document_id)
    try:
        db.table("chat_session_documents").upsert(
            {"session_id": session_id, "document_id": request.document_id},
        ).execute()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "session_id": session_id, "document_id": request.document_id}


@router.delete("/sessions/{session_id}/documents/{document_id}")
def detach_document(session_id: str, document_id: str):
    """Remove a document attachment from a chat session."""
    from ..db.supabase import get_db
    db = get_db()
    db.table("chat_session_documents").delete().eq("session_id", session_id).eq(
        "document_id", document_id
    ).execute()
    return {"status": "ok"}


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    user_id: str | None = None,
    folder_id: str | None = None,
):
    """Upload and ingest a PDF document. Stamps owner_id and (optionally) folder_id."""
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

        # Stamp ownership + non-global on user uploads.
        doc = (result or {}).get("document") or {}
        doc_id = doc.get("id")
        if doc_id:
            from ..db.supabase import get_db
            patch: dict = {"is_global": False}
            if user_id:
                patch["owner_id"] = user_id
            if folder_id:
                patch["folder_id"] = folder_id
            try:
                get_db().table("legal_documents").update(patch).eq("id", doc_id).execute()
            except Exception:
                # Non-fatal: ingestion succeeded, ownership stamp didn't.
                pass

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
