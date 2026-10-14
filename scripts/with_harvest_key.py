#!/usr/bin/env python3
"""Run a harvest script with a temporary OpenAI key, never the production one.

  backend/.venv/bin/python scripts/with_harvest_key.py scripts/harvest_court_decisions.py --court all ...

app.config loads backend/.env with override=True at import, so a key passed
on the command line is silently replaced by whatever .env holds. This loads
the config first, then swaps in HARVEST_OPENAI_API_KEY (from the environment
or the git-ignored backend/.env.harvest), clears the cached Settings, checks
the swap took, and runs the target script in this same process. It refuses
when the temporary key is missing or equals backend/.env's key: harvest
embeddings once exhausted the production credit and took all search down.
The same isolation as ingest_staged_parliament_acts.py.
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"


def _read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def configure_harvest_key() -> None:
    temporary = (os.environ.get("HARVEST_OPENAI_API_KEY", "").strip()
                 or _read_env_file(BACKEND / ".env.harvest").get("HARVEST_OPENAI_API_KEY", "").strip())
    if not temporary:
        raise SystemExit("Refusing: put a temporary, non-production OpenAI key in backend/.env.harvest "
                         "as HARVEST_OPENAI_API_KEY=...")
    production = _read_env_file(BACKEND / ".env").get("OPENAI_API_KEY", "").strip()
    if temporary == production or temporary == os.environ.get("OPENAI_API_KEY", "").strip():
        raise SystemExit("Refusing: HARVEST_OPENAI_API_KEY matches the production key. Use a separate key.")
    sys.path.insert(0, str(BACKEND))
    from app import config  # loads backend/.env (override=True) once, now
    os.environ["OPENAI_API_KEY"] = temporary
    os.environ["OPENAI_API_KEY_FALLBACK"] = ""
    os.environ["OPENAI_FALLBACK_BASE_URL"] = ""
    os.environ["EMBEDDING_PROVIDER"] = "openai"
    config.get_settings.cache_clear()
    settings = config.get_settings()
    if settings.openai_api_key != temporary or settings.openai_api_key_fallback:
        raise SystemExit("Refusing: temporary-key isolation check failed.")
    print("Harvest key isolation OK: embeddings use the temporary key, production key untouched.", flush=True)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    configure_harvest_key()
    target = sys.argv[1]
    sys.argv = sys.argv[1:]
    sys.path.insert(0, str(Path(target).resolve().parent))
    runpy.run_path(target, run_name="__main__")


if __name__ == "__main__":
    main()
