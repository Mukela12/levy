"""One answer per question, however many times the browser asks.

The agent run is detached on purpose: it finishes and saves even when the
reader's connection dies. That durability has a cost. When a stream drops
mid-answer the client shows an error and unlocks the composer, so the person
sends the same question again while the first run is still working, and both
runs answer it.

Measured on 21 September in session 890c96b0: one question, two complete
answers saved 3.4 seconds apart, both from a full tool-using run. Since the
server started repairing dropped question inserts on 13 September this is the
only remaining way a thread ends up with two answers and one question.

So a question already being answered for a session cannot start a second run.
The caller is told, and the existing client-side recovery, which polls for the
row the first run saves, gives the person the answer they were waiting for.

Kept in memory on purpose: the API runs as a single uvicorn process (see the
Procfile) and this only needs to cover the seconds-to-minutes a run is alive.
It fails OPEN in every uncertain case, because refusing a legitimate question
is far worse than answering a duplicate one.
"""
from __future__ import annotations

import hashlib
import time

# session_id + question -> when that run started.
_RUNS: dict[tuple[str, str], float] = {}

# The slowest run ever recorded was 402 seconds. Well past that an entry can
# only be a leak (a process paused mid-run, a task killed without its finally),
# and a stale entry must never block a real question.
STALE_AFTER_SECONDS = 900.0


def _key(session_id: str, query: str) -> tuple[str, str]:
    # Hashed so the registry never holds a person's question in memory, and
    # whitespace-normalised because a resend can differ by a trailing newline.
    text = " ".join((query or "").split())
    return session_id, hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sweep(now: float) -> None:
    for key, started in list(_RUNS.items()):
        if now - started > STALE_AFTER_SECONDS:
            _RUNS.pop(key, None)


def begin(session_id: str | None, query: str) -> bool:
    """Claim this question for this session. False means one is already running.

    Without a session there is nothing to key on (anonymous visitors have no
    thread), so the run is always allowed.
    """
    if not session_id or not (query or "").strip():
        return True
    now = time.time()
    _sweep(now)
    key = _key(session_id, query)
    if key in _RUNS:
        return False
    _RUNS[key] = now
    return True


def end(session_id: str | None, query: str) -> None:
    """Release the claim. Safe to call when begin() was never reached."""
    if not session_id or not (query or "").strip():
        return
    _RUNS.pop(_key(session_id, query), None)


def active_runs() -> int:
    """How many runs are currently claimed. For tests and health checks."""
    _sweep(time.time())
    return len(_RUNS)
