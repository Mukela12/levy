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
from .compactor import compact_if_needed
from .tools import (
    ToolCallRecord,
    build_tool_registry,
    execute_tool,
    to_anthropic_schema,
    truncate_for_model,
)


import time as _time

DEFAULT_MODEL = "claude-sonnet-4-20250514"

# Per-process cooldown bookkeeping: session_id -> monotonic timestamp of last
# compaction. Worker restarts wipe this naturally, which is fine.
_LAST_COMPACTION: dict[str, float] = {}
AGENT_SYSTEM_SUFFIX = """

You are operating as an agent with tool access. Use tools to answer the user.

Workflow — corpus-first, web on demand:
1. Call `search_corpus` once with a clear query for any substantive question.
2. ESCALATE TO WEB SEARCH AUTOMATICALLY when ANY of these is true:
   - search_corpus returned 0 matches.
   - The top similarity is low (under ~0.55) and the user's question is
     specific (asks for fees, deadlines, current procedure, an Act not in
     the corpus, a recent ruling, news, or how to do something practical).
   - The user explicitly asked about something current ("latest", "today",
     "as of now", "this year", new amendment).
   In any of those cases call `gov_search` (preferring Zambian-gov domains)
   without waiting for permission. If gov_search comes back thin, fall back
   to `web_search`. If a result snippet looks promising but truncated,
   `web_fetch` the full URL.
3. STOP gathering and WRITE THE ANSWER after at most 4 tool rounds. The
   user wants a usable answer, not a perfect one. Note any gaps in the
   answer itself.
4. Do not narrate "Let me search for X" between tool calls — just call the
   tool. Save your prose for the final answer.
5. Do not invent statutes, sections, page numbers, or fees. If you don't
   have it, say so explicitly.

When the user toggles the "Search" affordance on (signal in their message
or session) prefer web sources earlier and call gov_search alongside the
first corpus search rather than after.

When the user describes a real legal situation in Zambia and asks for
help bringing a case, filing an application, or seeking relief from a
court (e.g. "how do I sue my landlord", "I want to challenge my
dismissal", "can I get an urgent injunction", "we need letters of
administration", "judicial review of this tribunal decision"):

1. FIRST call `search_corpus` with terms close to the substantive area
   (e.g. "specific performance of a sale of land", "judicial review
   prerogative writs"). This grounds the procedural plan in the actual
   Zambian statutes / Rules in the corpus.
2. THEN call `recommend_application`. Fill every field. Choose the
   procedural mode that matches: most contested civil matters are
   Originating Notice of Motion or Writ + Statement of Claim;
   non-contentious / single-question disputes are Originating Summons;
   urgent reliefs without notice are Ex Parte Originating Notice of
   Motion. The UI renders this as a Plan card the user reviews.
3. Wait for the user to confirm. Do NOT proceed to draft Summons /
   Affidavits / Skeletal Arguments / Orders until the user accepts the
   plan. Once they accept, call the drafting tools in sequence — start
   with `draft_summons` (the originating process). For drafting tools you
   MUST have the parties' real names; if the user hasn't given them, ask
   first rather than inventing placeholders.

Standard Zambian filing heading you'll need to use throughout the
drafting tools:

    IN THE HIGH COURT FOR ZAMBIA
    AT THE [REGISTRY]
    HOLDEN AT [CITY]
    ([JURISDICTION e.g. Civil Jurisdiction])
                                          [YEAR]/[REGISTRY_CODE]/[NUMBER]
    BETWEEN:
    [PLAINTIFF / APPLICANT NAME]                       PLAINTIFF/APPLICANT
    AND
    [DEFENDANT / RESPONDENT NAME]                      DEFENDANT/RESPONDENT

Common registry codes: HPC (Principal Registry, Civil), HPCo
(Commercial), HK (Kitwe), HND (Ndola), HCH (Choma), HKS (Kasama). Cause
numbers from the user override these — never invent one; if not
supplied, leave it as `[CAUSE NUMBER TO BE ALLOCATED]` and note in your
prose that it'll be filled at filing.

When the user asks you to draft any document (memo, contract, NDA, demand
letter, brief, employment letter, anything document-shaped):
1. FIRST call `suggest_templates` with a short query describing what they
   want (e.g. "NDA"). The user may have a saved template — the UI shows
   returned templates as clickable cards. If the user already mentioned a
   specific template by name, pass that as the query.
2. If `suggest_templates` returns templates AND the user has NOT already
   chosen one, pause and ask: "I see X templates that might fit — would
   you like to use one of these or should I draft from scratch?" Do NOT
   call `pdf_generate` until the user picks or declines.
3. If the user declines templates, OR `suggest_templates` returns 0
   templates, proceed with `pdf_generate` from scratch.

When to produce artifacts (PDFs the user can download):
- `pdf_extract_pages` — when the user asks for "sections X to Y" or "the
  full text of the Companies Act provisions on directors". Use the
  document_id and page numbers from a prior `search_corpus` result.
- `pdf_generate` — when the user asks for a memo, brief, summary, opinion,
  or any document-shaped artifact (after the template-check above). Pass
  clean Markdown; headings, lists, tables, and blockquotes all render.
  Always include a title.
- `pdf_merge` — when the user wants to combine multiple sources, e.g.
  "compile a one-page memo plus the relevant Companies Act sections as an
  appendix". Pass parts in the order the final document should read.
- `pdf_split` — when the user asks for several focused excerpts at once,
  e.g. "give me sections 1-5, 12-18, and 30-34 of the Penal Code as
  separate PDFs". Each range becomes its own artifact card.
- `export_thread_brief` — when the user asks to "export this thread",
  "save this consultation as a PDF", "turn this into a brief", or anything
  semantically equivalent. Produces a single PDF: the Q&A transcript +
  an appendix containing the cited page ranges from every corpus document
  referenced in the thread. Always preferable to manually re-running
  pdf_generate for an export.

When to crawl the web instead of just searching:
- `web_crawl` — when one gov-source page is clearly an index (forms+fees
  hub, act listings) and the answer is one click in. Pass the seed URL
  from a prior `gov_search` and the agent fetches that page plus up to
  N in-domain links. Use sparingly; web_search/gov_search/web_fetch are
  cheaper for most questions.

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

        # Compact older history if we're approaching the model's window —
        # but respect the per-session cooldown so back-to-back tool rounds
        # don't trigger Haiku's 50K-input-tokens/min rate limit.
        cooldown_key = session_id or "_anon_"
        last_at = _LAST_COMPACTION.get(cooldown_key)
        in_cooldown = (
            last_at is not None
            and (_time.monotonic() - last_at) < settings.compaction_cooldown_seconds
        )
        if in_cooldown:
            compacted_messages, compaction_info = messages, None
        else:
            compacted_messages, compaction_info = await compact_if_needed(messages)
            if compaction_info and not compaction_info.get("error"):
                _LAST_COMPACTION[cooldown_key] = _time.monotonic()
        if compaction_info:
            yield {"type": "compaction", **compaction_info}

        # Streaming call. Capture tool_use blocks as they finalize, and forward
        # text deltas as `token` events.
        final_message = None
        try:
            async with client.messages.stream(
                model=model_name,
                max_tokens=4096,
                system=system_prompt,
                messages=compacted_messages,
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
            extras = envelope.get("extra_artifacts") or []
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
            for extra in extras:
                yield {"type": "artifact", "artifact": extra}

            # Surface the suggested templates so the UI can render clickable
            # cards inline in the chat. Tied to the originating tool_call_id
            # so the chronological reducer on the frontend can position the
            # cards immediately after the tool card.
            template_suggestions = envelope.get("templates")
            if template_suggestions:
                yield {
                    "type": "template_suggestion",
                    "tool_call_id": tool_id,
                    "templates": template_suggestions,
                }

            # Surface the application plan as a structured event so the UI
            # can render a Plan card inline (with cause of action, reliefs,
            # documents to file, etc.).
            application_plan = envelope.get("application_plan")
            if application_plan:
                yield {
                    "type": "application_plan",
                    "tool_call_id": tool_id,
                    "plan": application_plan,
                }

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
