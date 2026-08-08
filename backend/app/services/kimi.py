"""Moonshot Kimi as a cross-vendor fallback for the Levy agent.

WHY THIS EXISTS
---------------
Every model in Levy's fallback chain was an Anthropic model, so an Anthropic
outage — or simply hitting the org's rate limit during a busy hour — took Levy
down completely. Kimi is a different vendor on different infrastructure, so it
survives failures that no amount of Claude-to-Claude fallback can.

It is NOT here to save money. Benchmarked on Levy's real workload (the full
45k-char system prompt, all 27 tool schemas, questions taken verbatim from the
field study), Kimi came out MORE expensive per turn than Claude, not less:

    claude-haiku-4-5    $0.018      kimi-k2.6        $0.041
    claude-sonnet-4-6   $0.035      kimi-k2.7-code   $0.046

The sticker prices say the opposite ($0.95/$4.00 for Kimi vs $3.00/$15.00 for
Sonnet). Two things flip it on this particular workload:

  1. Prompt caching. Levy sends a very large fixed prefix and a short question.
     Anthropic serves that prefix at $0.30/MTok (Sonnet) or $0.10/MTok (Haiku)
     and engages reliably; in benchmarking Kimi's cache was inconsistent, with
     several calls billing all ~19k input tokens fresh at $0.95/MTok.
  2. Reasoning tokens. kimi-k2.6 is a reasoning model and spends 53-288
     reasoning tokens per turn, billed as output at $4.00/MTok, on top of the
     answer.

Quality was genuinely fine: both Kimi models emitted well-formed tool calls
against our schema and chose the right tool on 3 of 4 cases — matching Sonnet.
So this is a sound resilience option, and a poor cost-reduction one.

INTEGRATION NOTES
-----------------
* kimi-k2.6 REJECTS any temperature but 1 ("invalid temperature: only 1 is
  allowed for this model"), the same constraint Claude Opus 4.7+ has. Never
  send `temperature` here.
* The API is OpenAI-shaped, so this module translates Levy's Anthropic-shaped
  request in and translates the response back out, presenting the same duck
  type the agent loop already consumes.
* Fails closed: with no MOONSHOT_API_KEY configured, `is_configured()` is
  False and the agent never attempts this path.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, AsyncIterator

import httpx

from ..config import get_settings

BASE_URL = "https://api.moonshot.ai/v1/chat/completions"

# Default cross-vendor fallback. k2.6 is the general-purpose model; k2.7-code is
# tuned for agentic coding and is a poorer fit for legal Q&A.
DEFAULT_KIMI_MODEL = "kimi-k2.6"

# Model ids we recognise as Kimi, so the agent can route them here.
KIMI_MODELS = {"kimi-k2.6", "kimi-k2.7-code", "kimi-k3"}


def is_kimi_model(model: str) -> bool:
    return (model or "").strip().lower() in KIMI_MODELS


def is_configured() -> bool:
    """True only when a Moonshot key is set. No key, no fallback."""
    return bool((get_settings().moonshot_api_key or "").strip())


# ─── Request translation: Anthropic shape -> OpenAI shape ────────────────────


def _system_to_text(system: Any) -> str:
    """Anthropic accepts a list of text blocks (with cache_control); Kimi wants
    one string."""
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        return "\n\n".join(
            b.get("text", "") for b in system if isinstance(b, dict) and b.get("text")
        )
    return ""


def _tools_to_openai(tool_schemas: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
            },
        }
        for t in (tool_schemas or [])
    ]


def _messages_to_openai(messages: list[dict]) -> list[dict]:
    """Flatten Anthropic content blocks into OpenAI messages.

    Anthropic puts tool_use blocks inside an assistant message and tool_result
    blocks inside the following user message. OpenAI wants assistant messages
    carrying `tool_calls`, and each result as its own `role: "tool"` message.
    """
    out: list[dict] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")

        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        text_parts: list[str] = []
        tool_calls: list[dict] = []
        tool_results: list[dict] = []

        for block in content or []:
            # Blocks arrive either as dicts (our own history) or as SDK objects
            # (an assistant turn echoed straight back from Anthropic).
            btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            get = (lambda k, d=None, b=block: b.get(k, d)) if isinstance(block, dict) \
                else (lambda k, d=None, b=block: getattr(b, k, d))

            if btype == "text":
                text_parts.append(get("text") or "")
            elif btype == "tool_use":
                tool_calls.append({
                    "id": get("id"),
                    "type": "function",
                    "function": {
                        "name": get("name"),
                        "arguments": json.dumps(get("input") or {}),
                    },
                })
            elif btype == "tool_result":
                raw = get("content")
                if isinstance(raw, list):
                    raw = "\n".join(
                        (c.get("text", "") if isinstance(c, dict) else str(c)) for c in raw
                    )
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": get("tool_use_id"),
                    "content": raw if isinstance(raw, str) else json.dumps(raw),
                })

        if role == "assistant":
            msg: dict = {"role": "assistant", "content": "\n".join(p for p in text_parts if p)}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            out.append(msg)
        else:
            # Tool results must precede any accompanying user text.
            out.extend(tool_results)
            joined = "\n".join(p for p in text_parts if p)
            if joined:
                out.append({"role": "user", "content": joined})
    return out


# ─── Response translation: OpenAI shape -> the duck type the agent expects ────


def _to_final_message(payload: dict) -> SimpleNamespace:
    """Build an object shaped like an Anthropic Message.

    The agent loop reads `.content` (blocks with .type/.text/.name/.input/.id),
    `.usage.input_tokens` / `.output_tokens`, and `.stop_reason`.
    """
    choice = (payload.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    usage = payload.get("usage") or {}

    blocks: list[SimpleNamespace] = []
    text = msg.get("content") or ""
    if text:
        blocks.append(SimpleNamespace(type="text", text=text))

    for call in msg.get("tool_calls") or []:
        fn = call.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            # A malformed argument blob must not kill the run; surface it as an
            # empty call so the tool layer returns a normal error the model can
            # recover from.
            args = {}
        blocks.append(SimpleNamespace(
            type="tool_use", id=call.get("id"), name=fn.get("name"), input=args,
        ))

    finish = choice.get("finish_reason")
    stop_reason = "tool_use" if any(b.type == "tool_use" for b in blocks) else (
        "max_tokens" if finish == "length" else "end_turn"
    )

    return SimpleNamespace(
        content=blocks,
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=usage.get("prompt_tokens", 0) or 0,
            output_tokens=usage.get("completion_tokens", 0) or 0,
        ),
        model=payload.get("model"),
    )


class KimiError(RuntimeError):
    """Any Kimi-side failure, so the agent can treat it like an APIError."""


async def stream_kimi(
    *,
    model: str,
    system: Any,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int,
) -> AsyncIterator[dict]:
    """Run one Kimi turn, yielding token events then a final message.

    Yields `{"type": "token", "content": str}` for streamed text, and finally
    `{"type": "final", "message": <Anthropic-shaped object>}`.
    """
    settings = get_settings()
    key = (settings.moonshot_api_key or "").strip()
    if not key:
        raise KimiError("Moonshot API key is not configured")

    body = {
        "model": model,
        "messages": (
            ([{"role": "system", "content": _system_to_text(system)}] if system else [])
            + _messages_to_openai(messages)
        ),
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        # Deliberately NO temperature — kimi-k2.6 rejects anything but 1.
    }
    if tools:
        body["tools"] = _tools_to_openai(tools)

    text_acc = ""
    tool_acc: dict[int, dict] = {}
    usage: dict = {}
    finish_reason: str | None = None
    model_name = model

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=15.0)) as http:
            async with http.stream(
                "POST", BASE_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=body,
            ) as resp:
                if resp.status_code != 200:
                    detail = (await resp.aread()).decode(errors="replace")[:400]
                    raise KimiError(f"Kimi HTTP {resp.status_code}: {detail}")

                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    if chunk.get("model"):
                        model_name = chunk["model"]

                    for choice in chunk.get("choices") or []:
                        if choice.get("finish_reason"):
                            finish_reason = choice["finish_reason"]
                        delta = choice.get("delta") or {}

                        piece = delta.get("content")
                        if piece:
                            text_acc += piece
                            yield {"type": "token", "content": piece}

                        # Tool calls stream in fragments keyed by index; the name
                        # arrives once and the arguments accumulate.
                        for tc in delta.get("tool_calls") or []:
                            idx = tc.get("index", 0)
                            slot = tool_acc.setdefault(
                                idx, {"id": None, "function": {"name": None, "arguments": ""}})
                            if tc.get("id"):
                                slot["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                slot["function"]["name"] = fn["name"]
                            if fn.get("arguments"):
                                slot["function"]["arguments"] += fn["arguments"]
    except KimiError:
        raise
    except Exception as e:  # noqa: BLE001 — network/parse: surface as one error type
        raise KimiError(f"Kimi request failed: {type(e).__name__}: {e}") from e

    payload = {
        "model": model_name,
        "usage": usage,
        "choices": [{
            "finish_reason": finish_reason,
            "message": {
                "content": text_acc,
                "tool_calls": [
                    {"id": v["id"] or f"call_{i}", "type": "function", "function": v["function"]}
                    for i, v in sorted(tool_acc.items())
                    if v["function"]["name"]
                ],
            },
        }],
    }
    yield {"type": "final", "message": _to_final_message(payload)}
