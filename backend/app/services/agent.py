"""
Agent loop for Levy.

Drives the plan → tool-call → observe → respond cycle on top of Anthropic's
streaming `tool_use` API. Yields SSE-friendly event dicts that the route
handler turns into `data: {...}\n\n` lines.

Event shapes emitted to the client:
  {type: "thinking"}                                   first event of every turn
  {type: "tool_call", id, name, input}                 model invoked a tool
  {type: "tool_result", id, name, ok, db, web, ms}     tool finished
  {type: "token", content: "..."}                      streamed answer text
  {type: "sources", db: [...], web: [...]}             dedup'd sources for UI
  {type: "done", usage, timing, iterations}            loop terminated cleanly
  {type: "error", message}                             unrecoverable problem
"""

from __future__ import annotations

import json
import time
from typing import AsyncIterator

import anthropic

from ..config import get_settings
from ..prompts.legal_qa import SYSTEM_PROMPT
from .tools import (
    ToolCallRecord,
    build_tool_registry,
    execute_tool,
    to_anthropic_schema,
    truncate_for_model,
)


DEFAULT_MODEL = "claude-sonnet-4-20250514"
AGENT_SYSTEM_SUFFIX = """

You are operating as an agent with tool access. Use tools to answer the user.

Workflow — be decisive, not perfectionist:
1. Call `search_corpus` once with a clear query for any substantive question.
2. If web search is enabled and you genuinely lack key info (current fees,
   recent rulings), call `gov_search` ONCE. Only call it a second time with a
   reformulated query if the first returned nothing useful.
3. STOP gathering and WRITE THE ANSWER after at most 4 tool rounds. The user
   wants a usable answer based on what you found, not a perfect one. Note any
   gaps in the answer itself.
4. Do not narrate "Let me search for X" between tool calls — just call the
   tool. Save your prose for the final answer.
5. Do not invent statutes, sections, page numbers, or fees. If you don't have
   it, say so explicitly.

When to produce artifacts (PDFs the user can download):
- `pdf_extract_pages` — when the user asks for "sections X to Y" or "the
  full text of the Companies Act provisions on directors". Use the
  document_id and page numbers from a prior `search_corpus` result.
- `pdf_generate` — when the user asks for a memo, brief, summary, opinion,
  or any document-shaped artifact. Pass clean Markdown; headings, lists,
  tables, and blockquotes all render. Always include a title.
- `pdf_merge` — when the user wants to combine multiple sources, e.g.
  "compile a one-page memo plus the relevant Companies Act sections as an
  appendix". Pass parts in the order the final document should read.

Do NOT generate an artifact unless the user asked for one (explicitly or
implicitly via "draft a memo", "extract sections", "make a one-pager",
"prepare a brief"). Plain Q&A doesn't need an artifact.

Final answer format:
- Prose with inline citations: `[Companies Act, S.13] (p. 370)` for corpus,
  bare URLs for web results.
- If you produced an artifact, mention it briefly so the user knows to look
  at the artifact card (don't paste the full content into the chat reply).
- If the corpus didn't contain something, lead with what you DID find, then
  call out the gap, then suggest where the user can verify.
"""


async def run_agent(
    *,
    user_query: str,
    model: str | None = None,
    web_enabled: bool = False,
    history: list[dict] | None = None,
    owner_id: str | None = None,
    session_id: str | None = None,
    attached_doc_ids: list[str] | None = None,
) -> AsyncIterator[dict]:
    settings = get_settings()
    model_name = model or DEFAULT_MODEL
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # If a session is given, fetch its currently-attached docs from the DB so
    # the model's corpus search automatically sees them. The frontend can also
    # pass attached_doc_ids explicitly to short-circuit the lookup.
    if session_id and attached_doc_ids is None:
        try:
            from ..db.supabase import get_db
            res = (
                get_db()
                .table("chat_session_documents")
                .select("document_id")
                .eq("session_id", session_id)
                .execute()
            )
            attached_doc_ids = [r["document_id"] for r in (res.data or [])]
        except Exception:
            attached_doc_ids = []

    registry = build_tool_registry(
        web_enabled=web_enabled,
        owner_id=owner_id,
        session_id=session_id,
        attached_doc_ids=attached_doc_ids,
    )
    tool_schemas = to_anthropic_schema(registry)

    system_prompt = SYSTEM_PROMPT + AGENT_SYSTEM_SUFFIX

    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": user_query})

    started = time.monotonic()
    yield {"type": "thinking"}

    tool_calls: list[ToolCallRecord] = []
    db_sources_acc: dict[str, dict] = {}
    web_sources_acc: dict[str, dict] = {}
    total_input_tokens = 0
    total_output_tokens = 0
    iterations = 0

    while True:
        # If we hit the iteration cap, force a final answer with no tools so
        # the user always gets a written response from accumulated context.
        cap_reached = iterations >= settings.agent_max_iterations
        iterations += 1

        if cap_reached:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "You have reached the tool-call budget. Stop calling tools and "
                        "write your final answer now using only what you've already "
                        "gathered. Cite the sources you have. If something is missing, "
                        "say so explicitly."
                    ),
                }
            )

        # Streaming call. Capture tool_use blocks as they finalize, and forward
        # text deltas as `token` events.
        final_message = None
        try:
            async with client.messages.stream(
                model=model_name,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
                tools=[] if cap_reached else tool_schemas,
            ) as stream:
                async for event in stream:
                    etype = getattr(event, "type", None)
                    if etype == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if delta and getattr(delta, "type", None) == "text_delta":
                            yield {"type": "token", "content": delta.text}
                final_message = await stream.get_final_message()
        except anthropic.APIError as e:  # noqa: BLE001
            yield {"type": "error", "message": f"anthropic API error: {e}"}
            return

        if final_message is None:
            yield {"type": "error", "message": "no final message from model"}
            return

        if final_message.usage:
            total_input_tokens += final_message.usage.input_tokens or 0
            total_output_tokens += final_message.usage.output_tokens or 0

        # Append the assistant message to the conversation as Anthropic returned it
        # (preserving any tool_use blocks so the next user turn's tool_results match).
        messages.append({"role": "assistant", "content": final_message.content})

        # If the model is done talking, exit the loop.
        if final_message.stop_reason != "tool_use":
            break

        # Otherwise, execute every tool_use block in this assistant message
        # and append a single user message containing all tool_results.
        tool_results_content: list[dict] = []
        for block in final_message.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            tool_id = block.id
            tool_name = block.name
            tool_input = block.input or {}

            yield {
                "type": "tool_call",
                "id": tool_id,
                "name": tool_name,
                "input": tool_input,
            }

            t0 = time.monotonic()
            envelope = await execute_tool(
                registry,
                tool_name,
                tool_input,
                timeout_seconds=settings.agent_tool_timeout_seconds,
            )
            elapsed_ms = round((time.monotonic() - t0) * 1000)

            result = envelope.get("result", {})
            db = envelope.get("db_sources") or []
            web = envelope.get("web_sources") or []

            for s in db:
                key = s.get("id") or json.dumps(s, sort_keys=True)
                db_sources_acc[str(key)] = s
            for s in web:
                key = s.get("url") or json.dumps(s, sort_keys=True)
                web_sources_acc[str(key)] = s

            tool_calls.append(
                ToolCallRecord(
                    id=tool_id,
                    name=tool_name,
                    input=tool_input,
                    result=result if isinstance(result, dict) else {"value": result},
                    duration_ms=elapsed_ms,
                    db_sources=db,
                    web_sources=web,
                )
            )

            artifact = envelope.get("artifact")
            yield {
                "type": "tool_result",
                "id": tool_id,
                "name": tool_name,
                "ok": "error" not in (result if isinstance(result, dict) else {}),
                "db": db,
                "web": web,
                "artifact": artifact,
                "ms": elapsed_ms,
            }
            if artifact:
                yield {"type": "artifact", "artifact": artifact}

            tool_results_content.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": truncate_for_model(
                        envelope, settings.agent_max_tool_result_chars
                    ),
                }
            )

        messages.append({"role": "user", "content": tool_results_content})

    yield {
        "type": "sources",
        "db": list(db_sources_acc.values()),
        "web": list(web_sources_acc.values()),
    }

    yield {
        "type": "done",
        "usage": {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens},
        "timing": {"total_ms": round((time.monotonic() - started) * 1000)},
        "iterations": iterations,
        "model": model_name,
    }
