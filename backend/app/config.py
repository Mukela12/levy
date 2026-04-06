from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache
from dotenv import load_dotenv

# Load .env explicitly before pydantic-settings reads it
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE, override=True)


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # Voyage AI (for embeddings — legal-optimized)
    voyage_api_key: str = ""

    # Anthropic (for chat)
    anthropic_api_key: str = ""

    # Embedding config
    embedding_provider: str = "voyage"  # "voyage" or "local"
    embedding_dimensions: int = 1024  # voyage-law-2 = 1024, local bge = 768

    # RAG config
    retrieval_top_k: int = 5
    similarity_threshold: float = 0.7

    class Config:
        env_file = str(_ENV_FILE)
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
