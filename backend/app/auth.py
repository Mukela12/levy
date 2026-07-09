"""
Request authentication for the Levy API.

The backend talks to Supabase with the service_role key, which bypasses
Row-Level Security. That means the backend MUST authorize requests itself
— it cannot trust a `user_id` sent by the client. This module verifies the
caller's Supabase access token and returns the authenticated user id.

Verification strategy: call Supabase GoTrue `GET /auth/v1/user` with the
bearer token. Returns the user when the token is valid, 401 otherwise.
This needs no JWT secret (works with the project apikey we already have),
and a short in-process cache keeps it to ~one network call per token per
minute so it doesn't add latency to every request.
"""

from __future__ import annotations

import time
from typing import Optional

import httpx
from fastapi import Header, HTTPException

from .config import get_settings

# token -> (user_id, expires_at_monotonic)
_CACHE: dict[str, tuple[str, float]] = {}
_TTL = 60.0  # seconds


def _verify(token: str) -> Optional[str]:
    now = time.monotonic()
    hit = _CACHE.get(token)
    if hit and hit[1] > now:
        return hit[0]

    settings = get_settings()
    base = settings.supabase_url.rstrip("/")
    try:
        r = httpx.get(
            f"{base}/auth/v1/user",
            headers={
                "apikey": settings.supabase_key,
                "Authorization": f"Bearer {token}",
            },
            timeout=10.0,
        )
    except Exception:
        return None
    if r.status_code != 200:
        return None
    uid = (r.json() or {}).get("id")
    if not uid:
        return None
    _CACHE[token] = (uid, now + _TTL)
    # opportunistic cache prune
    if len(_CACHE) > 5000:
        for k, (_, exp) in list(_CACHE.items()):
            if exp <= now:
                _CACHE.pop(k, None)
    return uid


def _token_from_header(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return parts[1].strip()
    return None


def optional_user(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    """Return the authenticated user id, or None if no/invalid token.

    Use for endpoints that work for both signed-in and anonymous callers
    (e.g. chat: anonymous users get global-corpus-only answers).
    """
    token = _token_from_header(authorization)
    if not token:
        return None
    return _verify(token)


def require_user(authorization: Optional[str] = Header(default=None)) -> str:
    """Return the authenticated user id, or raise 401.

    Use for any endpoint that reads or mutates user-owned data.
    """
    token = _token_from_header(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="authentication required")
    uid = _verify(token)
    if not uid:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return uid


def verify_token(token: str) -> Optional[str]:
    """Programmatic helper (e.g. for the SSE endpoint that reads the body)."""
    return _verify(token)
