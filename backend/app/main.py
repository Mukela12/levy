"""
Levy — Zambian Legal AI Assistant

FastAPI application entry point.
Run with: uvicorn app.main:app --reload
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .routes.api import router as api_router

logger = logging.getLogger("levy")

# Interactive API docs advertise every endpoint — keep them off in
# production. Enable locally with LEVY_ENABLE_DOCS=1.
_docs_enabled = os.environ.get("LEVY_ENABLE_DOCS", "").strip() in ("1", "true", "yes")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Let in-flight answers finish before the process exits.

    Levy answers on a DETACHED task (`_drive()` in routes/api.py) so a run
    survives the user closing their tab, and only writes the assistant message
    to the database at the very end. That protects against a CLIENT
    disconnect. It did nothing for a SERVER shutdown: on every deploy, any run
    still mid-flight was killed before it reached `acc.save()`, so the user
    watched their answer stop mid-sentence and the thread was left with a
    question and no reply — the exact "no reply" failure that drove people
    away in the July field study, reintroduced by the act of deploying.

    A Levy turn is long: multi-step agent loops with corpus searches routinely
    take 20-60 seconds, and drafting turns longer, so the window is wide.

    `_INFLIGHT_RUNS` already held precisely the right set of tasks. It existed
    to keep strong references so asyncio could not garbage-collect a detached
    task; it was never awaited. Now it is.

    Pair this with RAILWAY_DEPLOYMENT_DRAINING_SECONDS set above the p95 turn
    length, or the platform kills the process before this hook can finish.
    """
    yield  # startup: nothing to do

    from .routes.api import _INFLIGHT_RUNS

    pending = [t for t in _INFLIGHT_RUNS if not t.done()]
    if not pending:
        return
    logger.info("shutdown: waiting for %d in-flight answer(s) to save", len(pending))
    try:
        done, still_running = await asyncio.wait(
            pending, timeout=SHUTDOWN_GRACE_SECONDS,
        )
        if still_running:
            # Bounded on purpose: a wedged run must not block the deploy
            # forever. Log it loudly, because each one is a user who lost an
            # answer and we should know the real number.
            logger.warning(
                "shutdown: %d run(s) did not finish within %ss; their answers are lost",
                len(still_running), SHUTDOWN_GRACE_SECONDS,
            )
        else:
            logger.info("shutdown: all in-flight answers saved")
    except Exception:  # noqa: BLE001 — never let cleanup block the exit
        logger.exception("shutdown: error while draining in-flight runs")


# Bounded so a wedged run cannot hold a deploy open indefinitely. Must be LESS
# than RAILWAY_DEPLOYMENT_DRAINING_SECONDS, or the platform SIGKILLs us first
# and the hook never completes.
SHUTDOWN_GRACE_SECONDS = int(os.environ.get("LEVY_SHUTDOWN_GRACE_SECONDS", "90"))

app = FastAPI(
    title="Levy",
    description="AI-powered Zambian legal research assistant using RAG",
    version="0.1.0",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
    lifespan=lifespan,
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
    """Liveness, plus WHICH CODE is serving.

    A narration fix sat committed and pushed while production served two-day-old
    code, and every external check was consistent with either world: a user hit
    the old behaviour at 18:07 and probes showed the new one an hour later, with
    nothing to say when the deploy actually landed. Railway injects the git SHA
    into the container, so exposing it makes "is my commit live?" a curl instead
    of an argument with the deploy dashboard's login screen.
    """
    return {
        "status": "ok",
        "commit": os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")[:7] or None,
    }


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


@app.get("/health/fallback")
async def health_fallback():
    """Is the cross-vendor fallback actually reachable?

    Every model in Levy's fallback chain used to be an Anthropic model on one
    account behind one rate limit, so nothing survived an Anthropic-wide event.
    Kimi is the cross-vendor last resort — but a fallback that has never been
    exercised is not a fallback, and this path only runs in production when
    Claude is already failing, which is the worst moment to discover the key is
    missing or the balance is empty.

    So: a real (tiny) generation against the configured Kimi model.
      200 {ok:true}                     — armed and answering
      200 {ok:false, reason:"not_configured"} — deliberately off, NOT an error
      503 {ok:false, reason:...}        — configured but broken; fix it now

    Point an uptime checker here alongside /health/llm and /health/embeddings.
    """
    from .config import get_settings
    from .services import kimi

    settings = get_settings()
    model = settings.kimi_fallback_model

    if not kimi.is_configured():
        # A deliberate off-state, not a failure: with no key the agent simply
        # never appends Kimi to the chain. 200 so a monitor doesn't page.
        return {"ok": False, "configured": False, "reason": "not_configured",
                "detail": "MOONSHOT_API_KEY is unset; the chain is Claude-only."}

    try:
        final = None
        async for ev in kimi.stream_kimi(
            model=model,
            system="Reply with the single word: ok",
            messages=[{"role": "user", "content": "ping"}],
            tools=[],
            max_tokens=64,   # k2.6 is a reasoning model; leave room for its
                             # reasoning tokens or it finishes on length alone
        ):
            if ev["type"] == "final":
                final = ev["message"]
        if final is None:
            raise kimi.KimiError("stream ended without a final message")
        return {"ok": True, "configured": True, "model": model,
                "output_tokens": final.usage.output_tokens}
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        low = msg.lower()
        reason = ("quota_or_billing" if ("insufficient balance" in low or "quota" in low)
                  else "auth" if ("401" in msg or "unauthorized" in low or "invalid api key" in low)
                  else "rate_limited" if "429" in msg
                  else "model_not_found" if "404" in msg
                  else "provider_error")
        return JSONResponse(
            status_code=503,
            content={"ok": False, "configured": True, "model": model, "reason": reason},
        )


@app.get("/health/embeddings")
def health_embeddings():
    """Synthetic embedding ping for uptime monitoring.

    Corpus search and case-law search both embed the user's query before the
    vector lookup. The primary provider now has a second route to the identical
    model, so an empty billing balance no longer takes search down; this ping
    also reports whether that fallback route is configured, so a monitor can
    warn when the safety net is absent. 200 {ok:true} on success, 503 otherwise.
    """
    try:
        from .services.embedder import get_query_embedding
        from .config import get_settings

        settings = get_settings()
        vec = get_query_embedding("ping")
        return {
            "ok": True,
            "provider": settings.embedding_provider,
            "dims": len(vec),
            "fallback_ready": bool(settings.openai_api_key_fallback),
        }
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
