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

    # Tavily (web search)
    tavily_api_key: str = ""

    # Agent loop
    agent_max_iterations: int = 12
    agent_tool_timeout_seconds: int = 25
    agent_max_tool_result_chars: int = 8000

    # Context management
    # Trigger compaction when the running input-token total approaches Claude
    # Sonnet 4's 200K window. We leave headroom for the new turn's tools +
    # response generation.
    compaction_threshold_tokens: int = 140_000
    # Always keep this many trailing messages verbatim — only older ones get
    # collapsed into the "thread brief".
    compaction_keep_last_n: int = 6
    # When a tool_result block in an older turn is bigger than this many
    # characters, replace its content with a short stub before sending to the
    # model. The full result still lives in chat_messages for the UI.
    compaction_old_tool_result_max_chars: int = 800
    # Cheap, fast model for the summarisation pass itself.
    compaction_model: str = "claude-haiku-4-5-20251001"
    # After a successful compaction, suppress further compactions in the same
    # process for this many seconds — protects against hitting Haiku's
    # 50K-input-tokens-per-minute rate limit when the agent loops fast.
    compaction_cooldown_seconds: int = 60

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
