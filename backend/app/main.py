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
