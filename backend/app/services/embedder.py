"""
Embedding Service — Multi-provider embedding system with automatic fallback.

Providers:
  1. Voyage AI (voyage-law-2) — Legal-optimized, 1024 dims.
  2. OpenAI (text-embedding-3-small) — Configurable dimensions; the project
     uses 768 to match the existing pgvector(768) schema.
  3. Local (BAAI/bge-base-en-v1.5) — Free fallback, 768 dims, CPU.

The selected provider is set by `EMBEDDING_PROVIDER` in .env. Each provider
falls back to local on hard failure (rate limit, network, quota).

IMPORTANT: All chunks in a single database must use the SAME embedding provider
AND the same dimensions, because vectors from different models are NOT
comparable. Switching providers means re-ingesting all documents.
"""

import time
from ..config import get_settings

# Lazy-loaded clients (initialized on first use)
_voyage_client = None
_openai_client = None
_local_model = None


# ─── Voyage AI Provider ─────────────────────────────────────────────────

def _get_voyage_client():
    global _voyage_client
    if _voyage_client is None:
        import voyageai
        settings = get_settings()
        _voyage_client = voyageai.Client(api_key=settings.voyage_api_key)
    return _voyage_client


def _voyage_embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """
    Generate embeddings using Voyage AI's voyage-law-2 model.

    input_type: "document" for chunks being stored, "query" for search queries.
    Voyage uses this hint to optimize embeddings for retrieval.
    """
    client = _get_voyage_client()
    all_embeddings = []

    # Voyage supports up to 128 texts per batch
    batch_size = 128
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        result = client.embed(batch, model="voyage-law-2", input_type=input_type)
        all_embeddings.extend(result.embeddings)

    return all_embeddings


# ─── OpenAI Provider ─────────────────────────────────────────────────────

def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        settings = get_settings()
        _openai_client = OpenAI(api_key=settings.openai_api_key)
    return _openai_client


def _openai_embed(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings using OpenAI text-embedding-3-small (or whatever
    `openai_embedding_model` is configured), reduced to the configured
    `embedding_dimensions` so the vectors fit the existing pgvector schema.
    """
    client = _get_openai_client()
    settings = get_settings()
    model = settings.openai_embedding_model
    dims = settings.embedding_dimensions

    all_embeddings: list[list[float]] = []
    # OpenAI handles batches; cap at 256 to stay comfortably under the
    # 8192-token-per-request input budget for short legal chunks.
    batch_size = 256
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(model=model, input=batch, dimensions=dims)
        all_embeddings.extend([d.embedding for d in resp.data])
    return all_embeddings


# ─── Local Model Provider ────────────────────────────────────────────────

def _get_local_model():
    global _local_model
    if _local_model is None:
        print("  Loading local embedding model (first time may take a minute)...")
        from sentence_transformers import SentenceTransformer
        _local_model = SentenceTransformer("BAAI/bge-base-en-v1.5")
        print("  Local model loaded.")
    return _local_model


def _local_embed(texts: list[str]) -> list[list[float]]:
    """Generate embeddings using the local BGE model."""
    model = _get_local_model()
    embeddings = model.encode(texts, show_progress_bar=len(texts) > 10)
    return [e.tolist() for e in embeddings]


# ─── Public API (with fallback) ──────────────────────────────────────────

def get_embeddings(texts: list[str], batch_size: int = 128) -> list[list[float]]:
    """
    Generate embeddings for a list of texts.

    Tries Voyage AI first, falls back to local model if Voyage fails.
    Prints which provider was used for transparency.
    """
    settings = get_settings()
    provider = settings.embedding_provider

    if provider == "voyage":
        try:
            print(f"  Using Voyage AI (voyage-law-2) for {len(texts)} texts...")
            t0 = time.time()
            result = _voyage_embed(texts, input_type="document")
            elapsed = time.time() - t0
            print(f"  Voyage: {len(result)} embeddings in {elapsed:.1f}s ({len(result[0])} dims)")
            return result
        except Exception as e:
            print(f"  Voyage failed: {e}")
            print(f"  Falling back to local model...")
            return _local_embed(texts)

    elif provider == "openai":
        try:
            print(f"  Using OpenAI ({settings.openai_embedding_model}) for {len(texts)} texts...")
            t0 = time.time()
            result = _openai_embed(texts)
            elapsed = time.time() - t0
            print(f"  OpenAI: {len(result)} embeddings in {elapsed:.1f}s ({len(result[0])} dims)")
            return result
        except Exception as e:
            print(f"  OpenAI failed: {e}")
            print(f"  Falling back to local model...")
            return _local_embed(texts)

    elif provider == "local":
        print(f"  Using local model for {len(texts)} texts...")
        t0 = time.time()
        result = _local_embed(texts)
        elapsed = time.time() - t0
        print(f"  Local: {len(result)} embeddings in {elapsed:.1f}s ({len(result[0])} dims)")
        return result

    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


def get_query_embedding(query: str) -> list[float]:
    """
    Generate embedding for a single search query.

    Uses input_type="query" for Voyage (optimizes for retrieval).
    """
    settings = get_settings()
    provider = settings.embedding_provider

    if provider == "voyage":
        try:
            result = _voyage_embed([query], input_type="query")
            return result[0]
        except Exception as e:
            print(f"  Voyage query embedding failed: {e}, using local fallback")
            return _local_embed([query])[0]

    elif provider == "openai":
        try:
            return _openai_embed([query])[0]
        except Exception as e:
            print(f"  OpenAI query embedding failed: {e}, using local fallback")
            return _local_embed([query])[0]

    elif provider == "local":
        return _local_embed([query])[0]

    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


def get_embedding_dimensions() -> int:
    """Return the dimension count for the current provider."""
    settings = get_settings()
    return settings.embedding_dimensions
