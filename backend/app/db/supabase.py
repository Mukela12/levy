"""
Supabase Database Client — Handles all database operations for Levy.
"""

from supabase import create_client, Client
from ..config import get_settings


_client: Client | None = None


def get_db() -> Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client


def insert_document(data: dict) -> dict:
    """Insert a legal document record and return it with generated ID."""
    db = get_db()
    result = db.table("legal_documents").insert(data).execute()
    return result.data[0]


def insert_hierarchy_nodes(nodes: list[dict]) -> list[dict]:
    """Insert hierarchy nodes (parts, sections, subsections)."""
    db = get_db()
    result = db.table("legal_hierarchy").insert(nodes).execute()
    return result.data


def insert_chunks(chunks: list[dict]) -> list[dict]:
    """Insert legal chunks with embeddings."""
    db = get_db()
    # Supabase has a row limit per insert, batch in groups of 50
    all_results = []
    for i in range(0, len(chunks), 50):
        batch = chunks[i : i + 50]
        result = db.table("legal_chunks").insert(batch).execute()
        all_results.extend(result.data)
    return all_results


def search_chunks(query_embedding: list[float], top_k: int = 5, threshold: float = 0.7) -> list[dict]:
    """Vector similarity search using pgvector via Supabase RPC."""
    db = get_db()
    result = db.rpc(
        "search_legal_chunks",
        {
            "query_embedding": query_embedding,
            "match_count": top_k,
            "match_threshold": threshold,
        },
    ).execute()
    return result.data


def get_document_by_hash(pdf_hash: str) -> dict | None:
    """Check if a document has already been ingested."""
    db = get_db()
    result = (
        db.table("legal_documents")
        .select("*")
        .eq("pdf_hash", pdf_hash)
        .execute()
    )
    return result.data[0] if result.data else None


def get_chunk_with_hierarchy(chunk_id: str) -> dict | None:
    """Get a chunk with its full hierarchy path for citation."""
    db = get_db()
    chunk = db.table("legal_chunks").select("*, legal_hierarchy(*)").eq("id", chunk_id).execute()
    if not chunk.data:
        return None
    return chunk.data[0]


def get_document_stats() -> list[dict]:
    """Get summary stats for all ingested documents."""
    db = get_db()
    result = db.table("legal_documents").select("*").execute()
    return result.data
