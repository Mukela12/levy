"""
Levy — Zambian Legal AI Assistant

FastAPI application entry point.
Run with: uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes.api import router as api_router

app = FastAPI(
    title="Levy",
    description="AI-powered Zambian legal research assistant using RAG",
    version="0.1.0",
)

# CORS — allow frontend to connect (permissive for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
