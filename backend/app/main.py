"""
Levy — Zambian Legal AI Assistant

FastAPI application entry point.
Run with: uvicorn app.main:app --reload
"""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .routes.api import router as api_router

logger = logging.getLogger("levy")

# Interactive API docs advertise every endpoint — keep them off in
# production. Enable locally with LEVY_ENABLE_DOCS=1.
_docs_enabled = os.environ.get("LEVY_ENABLE_DOCS", "").strip() in ("1", "true", "yes")

app = FastAPI(
    title="Levy",
    description="AI-powered Zambian legal research assistant using RAG",
    version="0.1.0",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# CORS — restrict to our own frontends. The API authenticates with a bearer
# token (not cookies), but a wildcard origin lets any website script the API
# in a victim's browser, so pin the known origins + Vercel preview deploys.
_allowed_origins = [
    "https://levy-ten.vercel.app",
    "https://levylegal.ai",
    "https://www.levylegal.ai",
    "http://localhost:3000",
    "http://localhost:3001",
]
_extra = os.environ.get("ALLOWED_ORIGINS", "")
if _extra:
    _allowed_origins += [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"https://levy-[a-z0-9-]+\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Token"],
)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    """Never leak internal error detail (stack traces, DB messages, paths)
    to clients. Log the real error server-side; return a generic 500."""
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


# Register API routes
app.include_router(api_router)


@app.get("/")
def root():
    return {
        "name": "Levy",
        "version": "0.1.0",
        "description": "Zambian Legal AI Assistant",
        "endpoints": {
            "chat": "POST /api/chat",
            "search": "POST /api/search",
            "documents": "GET /api/documents",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/llm")
def health_llm():
    """Synthetic LLM ping for uptime monitoring.

    Does a tiny, cheap generation against the configured default model so an
    external monitor catches a retired model id, an empty credit balance, or a
    bad API key automatically — instead of us finding out from conversation
    logs days later. Returns 200 {ok:true} on success, 503 {ok:false,...} on
    any provider failure. Point an uptime checker (or a cron) at this path.
    """
    try:
        import anthropic
        from .config import get_settings
        from .providers.anthropic_provider import DEFAULT_MODEL

        settings = get_settings()
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=5,
            messages=[{"role": "user", "content": "ping"}],
        )
        return {"ok": True, "model": DEFAULT_MODEL}
    except Exception as e:
        from .providers.anthropic_provider import DEFAULT_MODEL
        status = getattr(e, "status_code", None)
        reason = "model_not_found" if (status == 404 or "not_found" in str(e).lower()) else (
            "rate_limited" if status == 429 else (
                "credit_or_bad_request" if status == 400 else "provider_error"
            )
        )
        return JSONResponse(
            status_code=503,
            content={"ok": False, "model": DEFAULT_MODEL, "reason": reason},
        )


@app.get("/health/embeddings")
def health_embeddings():
    """Synthetic embedding ping for uptime monitoring.

    Corpus search and case-law search both embed the user's query before the
    vector lookup, and the corpus is embedded with one provider (no compatible
    fallback). If that provider's quota is exhausted or its key is bad, every
    search fails while chat's LLM still answers, so it is easy to miss. Point
    an uptime checker at this path. 200 {ok:true} on success, 503 otherwise.
    """
    try:
        from .services.embedder import get_query_embedding
        from .config import get_settings

        vec = get_query_embedding("ping")
        return {"ok": True, "provider": get_settings().embedding_provider, "dims": len(vec)}
    except Exception as e:
        from .config import get_settings

        s = str(e).lower()
        reason = (
            "quota_or_billing" if ("insufficient_quota" in s or "quota" in s)
            else "rate_limited" if ("429" in s or "rate limit" in s)
            else "auth" if ("401" in s or "invalid api key" in s or "incorrect api key" in s)
            else "provider_error"
        )
        try:
            provider = get_settings().embedding_provider
        except Exception:
            provider = "unknown"
        return JSONResponse(
            status_code=503,
            content={"ok": False, "provider": provider, "reason": reason},
        )
