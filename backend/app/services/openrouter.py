"""OpenRouter as the last hop in the agent's model chain.

WHY THIS EXISTS
---------------
The chain is Levy's Claude models on Levy's Anthropic account, then Kimi if a
Moonshot key is set. When Anthropic credit ran out on 16 August 2026 chat went
down, and a Moonshot key is not always set. OpenRouter is billed separately,
serves Claude from Google Vertex and Amazon Bedrock as well as Anthropic, and
has free models, so it covers both an empty Anthropic balance and an Anthropic
outage.

Two hops, in order:

  1. `openrouter_fallback_model`, a paid Claude Sonnet. Sonnet 5.5 costs $2 in
     and $10 out per million tokens there (2 Oct 2026), cheaper than Sonnet 4.6
     on Levy's own account, with caching at $0.20. When the OpenRouter balance
     is spent this returns HTTP 402 and the chain moves on, so the balance
     never has to be checked in advance.
  2. `openrouter_free_model`, `openrouter/free`: a router over free models.
     Capped at 50 requests a day until 10 credits have been bought (1,000
     after), 20 a minute, and it can pick a different model each round. A last
     resort, not a product.

PRIVACY
-------
Levy prompts carry clients' facts, and many endpoints, free ones especially,
keep or train on prompts. Every request sends
`provider: {"zdr": true, "data_collection": "deny"}`, so OpenRouter only routes
to zero-retention endpoints. For Sonnet 5.5 that means Vertex or Bedrock; the
free models that train on prompts are refused rather than used.

LIMITS
------
* Requests go out in OpenAI's shape (kimi.py translates), so page images from
  read_pdf_pages are dropped on this path, as on Kimi.
* No extended thinking: replaying thinking blocks across tool rounds needs
  signatures the translation does not carry.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from ..config import get_settings
from . import kimi

BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
PRIVACY = {"zdr": True, "data_collection": "deny"}
# 429: rate limited (free models often are, upstream). 502/503: no provider
# up. 408: timed out upstream. Anything else moves straight down the chain.
RETRY_STATUSES = frozenset({408, 429, 502, 503})


class OpenRouterError(RuntimeError):
    """Any OpenRouter-side failure, so the agent can move down the chain."""


def is_configured() -> bool:
    return bool((get_settings().openrouter_api_key or "").strip())


def chain() -> list[str]:
    """The OpenRouter models to try, paid first. Empty with no key."""
    if not is_configured():
        return []
    s = get_settings()
    out: list[str] = []
    for m in (s.openrouter_fallback_model, s.openrouter_free_model):
        m = (m or "").strip()
        if m and m not in out:
            out.append(m)
    return out


def is_openrouter_model(model: str) -> bool:
    """OpenRouter ids are author/slug. Anthropic and Moonshot ids never have a
    slash, so the chain can route on it."""
    return "/" in (model or "")


async def stream_openrouter(
    *,
    model: str,
    system: Any,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int,
) -> AsyncIterator[dict]:
    """One OpenRouter turn: token events, then a final Anthropic-shaped message."""
    settings = get_settings()
    key = (settings.openrouter_api_key or "").strip()
    if not key:
        raise OpenRouterError("OpenRouter API key is not configured")
    body = kimi.chat_body(model=model, system=system, messages=messages, tools=tools,
                          max_tokens=max_tokens, cache=model.startswith("anthropic/"))
    body["provider"] = dict(PRIVACY)
    body["usage"] = {"include": True}  # cost per call, for the log line
    headers = {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://www.levylegal.ai",
        "X-Title": "Levy",
    }
    async for ev in kimi.stream_chat(
        url=BASE_URL, headers=headers, body=body, error=OpenRouterError,
        label="openrouter", retries=max(0, settings.openrouter_retries),
        retry_statuses=RETRY_STATUSES,
    ):
        yield ev
