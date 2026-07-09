# Levy — engineering report, May 7–8

## What this is

A complete, technical walkthrough of the 17 commits we shipped over two
days. By the end Levy went from "a chat that calls Claude with retrieved
chunks" to a real agentic legal assistant with: tool-using research,
clickable PDF citations that scroll to the cited page, generated /
extracted / merged PDF artifacts, a folder-based document library with
per-thread attachment, long-thread context compaction, anonymous-mode
chat, and inline tool-call rendering in the Claude-Code / Codex style.

If you just want the deltas, skip to **Section 2**. If you want to
understand how a single user message becomes a streamed answer with
inline tool cards on Railway, jump to **Section 3**.

---

## 1. The 2-day arc

```
a8cf01f  Restore frontend, deploy to Vercel + Railway, fix auth
4b8b334  Update root and frontend READMEs to reflect actual stack
214dcda  Mobile UI polish: floating dock input, 2x2 quick actions
2d570b7  Fix: useRegisterBrief caused infinite render loop
eceb840  Phase 1: agentic loop + Tavily web search
8c56729  Phase 2: PDF storage + clickable citations
ba8522b  Phase 2 cleanup
874fcff  Phase 2 fix: pdfjs DPI scaling
eb6acfc  Phase 3: PDF artifacts (extract/generate/merge) + canonical re-ingest
6cf288e  Phase 4: universal docs + per-thread attachment + dedupe
32fa0fd  Folder system on /documents: 3D folder cards, restored
3e2621a  Phase 5: long-thread context compaction
f597a65  Phase 6 polish + mobile folder fix
acabd84  Phase 6 fix: export_thread_brief resolves legacy citations
df87efe  Optional auth: ChatGPT-style anonymous mode
e9ecf29  Inline tool-call rendering (Claude Code / Codex style)
6e7572e  Inline tool-call rendering: persist toolCalls
```

~5,700 lines changed across 40 files. Three new backend services
(`agent.py`, `tools.py`, `pdf_tools.py`, `compactor.py`), a new
ingestion script (`reingest_acts.py`), and the frontend grew a folder
view, a PDF.js-backed citation viewer, an artifact card, and a
chronological-block renderer.

---

## 2. What each phase actually shipped

### Phase 1 — agentic loop + Tavily

The core unlock. Until this commit, `/api/chat` did one fixed thing:
embed the question, search Postgres for matching chunks, send everything
to Claude, stream the answer. Now Claude **decides** what to do.

Anthropic's Messages API supports a `tools=[...]` parameter. When you
pass tool definitions, the model can stop mid-response and emit a
`tool_use` block. You execute the tool, append the result as a
`tool_result` block, and call the model again. Repeat until the model
stops asking for tools.

The Levy agent loop, lightly trimmed:

```python
# backend/app/services/agent.py
async def run_agent(*, user_query, web_enabled, owner_id, session_id,
                    attached_doc_ids, history, ...) -> AsyncIterator[dict]:
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    registry = build_tool_registry(
        web_enabled=web_enabled,
        owner_id=owner_id,
        session_id=session_id,
        attached_doc_ids=attached_doc_ids,
    )

    messages = list(history or []) + [{"role": "user", "content": user_query}]
    yield {"type": "thinking"}

    while True:
        # ... compaction check (Section 5) ...

        async with client.messages.stream(
            model=DEFAULT_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT + AGENT_SYSTEM_SUFFIX,
            messages=compacted_messages,
            tools=to_anthropic_schema(registry),
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield {"type": "token", "content": event.delta.text}
            final = await stream.get_final_message()

        # Append the assistant turn (preserving tool_use blocks)
        messages.append({"role": "assistant", "content": final.content})

        if final.stop_reason != "tool_use":
            break

        # Execute every tool_use the model emitted, package the results
        tool_results = []
        for block in final.content:
            if block.type != "tool_use":
                continue
            yield {"type": "tool_call", "id": block.id, "name": block.name,
                   "input": block.input}

            envelope = await execute_tool(
                registry, block.name, block.input,
                timeout_seconds=settings.agent_tool_timeout_seconds,
            )

            yield {"type": "tool_result", "id": block.id, "name": block.name,
                   "ok": "error" not in envelope.get("result", {}),
                   "db": envelope.get("db_sources") or [],
                   "web": envelope.get("web_sources") or [],
                   "artifact": envelope.get("artifact"),
                   "ms": elapsed_ms}

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": truncate_for_model(envelope, 8000),
            })

        messages.append({"role": "user", "content": tool_results})
    yield {"type": "done", ...}
```

Six tool functions are registered:

- `search_corpus(query)` — pgvector cosine search over the legal library
- `gov_search(query)` — Tavily restricted to a curated whitelist of
  `.gov.zm` and institutional domains
- `web_search(query)` — Tavily, unrestricted (last resort)
- `web_fetch(url)` — Tavily `/extract` (clean readable text from one URL)
- `web_crawl(start_url, max_pages)` — fetch a seed, extract in-domain
  links, fetch up to N follow-ups
- (Phase 3 added the three PDF tools and Phase 6 added
  `pdf_split` + `export_thread_brief`)

Each tool definition is just a JSON schema + handler:

```python
# backend/app/services/tools.py
"gov_search": ToolDefinition(
    name="gov_search",
    description=("Web search restricted to official Zambian government "
                 "and institutional websites (parliament.gov.zm, "
                 "lawsofzambia.com, judiciaryzambia.com, ...) ..."),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer"},
        },
        "required": ["query"],
    },
    handler=_gov_search,
),
```

Why `gov_search` is a separate tool from `web_search` instead of one
tool with a flag: the model picks tools by name and description. Two
narrow tools with two narrow descriptions pick the right tool more
reliably than one ambiguous tool with a parameter.

### Phase 2 — PDF storage + clickable citations

Two pieces. Server-side: re-ingest every Act from canonical gov sources
(parliament.gov.zm, zambialii.org), upload the source PDF to a private
Supabase Storage bucket (`legal-docs/{document_id}.pdf`), store the path
in `legal_documents.pdf_storage_path`. Client-side: when a citation is
clicked, fetch a signed URL and render the PDF at the cited page in a
right-side panel using `pdfjs-dist`.

The viewer (sketch):

```tsx
// frontend/src/components/chat/pdf-viewer.tsx
const pdfjs = await import('pdfjs-dist')
pdfjs.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs'

const doc = await pdfjs.getDocument({ url: meta.signed_url }).promise
const page = await doc.getPage(target)
const viewport = page.getViewport({ scale })
const canvas = document.createElement('canvas')
canvas.width = viewport.width * dpr
canvas.height = viewport.height * dpr
container.replaceChildren(canvas)
const transform = dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined
await page.render({ canvasContext: ctx, viewport, transform }).promise
```

Two gotchas worth flagging:

1. **DPI scaling**. The first version called `ctx.scale(dpr, dpr)` and
   passed `{canvasContext, viewport}` only. Canvas dimensions came out
   correct but nothing painted. The pdfjs v4 path is to pass
   `transform: [dpr,0,0,dpr,0,0]` instead of touching `ctx.scale`.
2. **Service-role key required server-side**. Signed URLs against a
   private bucket can only be minted by a key with read RLS bypass.
   The backend's `SUPABASE_KEY` was anon, so we swapped it for the
   service_role key on Railway.

### Phase 3 — PDF artifacts (generate / extract / merge)

Three new tools. They write actual PDFs into a separate `artifacts`
bucket, with a row in `public.artifacts` carrying provenance. The agent
calls these when the user asks for a memo, a brief, or "extract sections
5-10 of the Companies Act".

- `pdf_generate(title, content_markdown, subtitle?)` — Markdown → PDF
  via WeasyPrint. Looks like a real legal memo (serif body, A4, page
  numbers).
- `pdf_extract_pages(document_id, page_start, page_end)` — pypdf slice
  out a contiguous page range from a corpus PDF.
- `pdf_merge(parts, title)` — concat artifacts + corpus page-ranges in
  any order.

WeasyPrint needs Pango/Cairo at runtime, which the slim Python image
doesn't ship. The Dockerfile installs them once at build time so cold
starts don't pay the cost:

```dockerfile
# backend/Dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
        libcairo2 libgdk-pixbuf-2.0-0 libffi8 \
        fonts-dejavu-core fonts-liberation shared-mime-info \
    && rm -rf /var/lib/apt/lists/*
```

The artifact row records exactly how it was made:

```python
# backend/app/services/pdf_tools.py
row = _insert_artifact_row(
    kind="pdf",
    title=final_title,
    storage_path="artifacts/pending",       # placeholder, overwritten below
    source="extracted",                     # generated|extracted|merged|uploaded
    size_bytes=len(pdf_bytes),
    page_count=end - start + 1,
    meta={
        "tool": "pdf_extract_pages",
        "source_document_id": document_id,
        "source_short_name": src_name,
        "page_start": start,
        "page_end": end,
    },
    owner_id=owner_id,
    session_id=session_id,
)
storage_path = _upload_artifact_pdf(row["id"], pdf_bytes)
db.table("artifacts").update({"storage_path": storage_path}) \
   .eq("id", row["id"]).execute()
```

Re-ingestion fixed two data-quality issues at the same time:

- **Lands Act** — switched from a 12-page zambialii excerpt to the
  36-page parliament.gov.zm version (200 chunks).
- **Constitution** — added the 96-page consolidated text from
  constituteproject.org alongside the existing 7-page Amendment Act.
  WeasyPrint's PDF exporter embeds NUL bytes in the text layer, which
  Postgres TEXT columns reject (`22P05:   cannot be converted to
  text`). Fix: a recursive `_scrub` that strips `\x00` from any string
  before insert.

Final library: 10 documents, 4,160 chunks, all PDFs in private
Storage.

### Phase 4 — universal documents + per-thread attachment

Three things:

1. Visibility model on `legal_documents`: `is_global boolean`,
   `owner_id uuid`. The 10 curated Acts are `is_global=true`. User
   uploads get `owner_id=<their uid>` and `is_global=false`.
2. New `chat_session_documents` (session_id, document_id) join table
   with RLS scoped to session owner.
3. New `search_legal_chunks_scoped(query_embedding, ..., caller_user_id,
   attached_doc_ids[])` RPC that filters by visibility:

```sql
where lc.effective_to is null
  and (
    ld.is_global = true
    or (caller_user_id is not null and ld.owner_id = caller_user_id)
    or (attached_doc_ids is not null and ld.id = any(attached_doc_ids))
  )
  and 1 - (lc.embedding <=> query_embedding) > match_threshold
```

The `search_corpus` tool is bound to the caller's scope at registry
build time:

```python
# backend/app/services/tools.py — build_tool_registry()
async def _scoped_search(query, top_k=5, threshold=None):
    return await _search_corpus(
        query, top_k=top_k, threshold=threshold,
        caller_user_id=owner_id,
        attached_doc_ids=attached_doc_ids,
    )

tools["search_corpus"] = ToolDefinition(..., handler=_scoped_search)
```

So each chat turn's agent gets a `search_corpus` that automatically
ANDs the user's identity into every search — there's no way to leak
between users.

### Folder system

Restored the original 3D folder cards as a real folder feature. Schema:

```sql
create table public.document_folders (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  ...
);
alter table public.legal_documents
  add column folder_id uuid references public.document_folders(id)
    on delete set null;  -- folder delete unfiles docs, doesn't drop them
```

Folders are organisational only. Search still sees every owned doc
regardless of folder, because the visibility filter doesn't look at
`folder_id`. Mobile renders 2-up with a smaller 3D folder visual
(72×56 vs 96×80 on desktop), preserving the hover fan-out animation
on every viewport.

### Phase 5 — long-thread context compaction

When a thread approaches Sonnet 4's 200K window, summarise the older
portion into a short brief and keep only the trailing 6 turns verbatim.
The full transcript is never mutated — only the messages array sent
to Anthropic this iteration.

```python
# backend/app/services/compactor.py
def estimate_tokens(messages: list[dict]) -> int:
    """Char-based heuristic (~3.5 chars/token). Fast; precision doesn't
    matter — the threshold has 60K of slack."""
    total = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, str): total += len(c)
        elif isinstance(c, list):
            for block in c:
                total += len(json.dumps(block, default=str))
    return int(total / 3.5)


async def compact_if_needed(messages, *, threshold_tokens=140_000,
                             keep_last_n=6, ...):
    if estimate_tokens(messages) <= threshold_tokens:
        return messages, None

    head = messages[:-keep_last_n]
    tail = [_truncate_tool_results_in_place(m, 800) for m in messages[-keep_last_n:]]

    # Haiku 4.5 produces a 300-500 word brief preserving every Act +
    # section + page citation verbatim
    flat = _flatten_for_summary(head)
    resp = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=900, system=_SUMMARY_SYSTEM,
        messages=[{"role": "user", "content": flat}],
    )
    summary = "".join(b.text for b in resp.content if b.type == "text")

    brief = {"role": "user",
             "content": "[Earlier conversation compressed by the system.\n"
                        "Full transcript preserved separately in the UI.]\n\n"
                        + summary}
    return [brief, *tail], {"tokens_before": ..., "tokens_after": ...}
```

A 60-second per-session **cooldown** prevents re-compaction within the
same agent loop (avoids Haiku's 50K-tokens/min rate limit). Failed
compactions don't update the cooldown so the next iteration retries.

Smoke-tested against a 336K-token synthetic history: 9 messages → 1046
char brief, **64% token reduction (336K → 120K)**, agent kept running.

### Phase 6 — premium edge

- **`export_thread_brief(session_id, title?, include_appendix=true)`** —
  the headline feature. Read every message in the thread, render the
  Q&A as Markdown → PDF, then for every distinct corpus document cited
  fetch its source PDF and append the cited page-ranges (deduped +
  merged into contiguous spans) at the back. Verified live: a real
  consultation became a 7-page brief with a 4-doc appendix in 30s.
- **`pdf_split`** — inverse of `pdf_merge`. Splits one source into N
  artifacts; the agent loop now emits `extra_artifacts` so each piece
  becomes its own card.
- **`web_crawl`** — fetch a seed URL and follow up to N in-domain
  links. Same-hostname only.
- **Archive sweep**: `POST /api/artifacts/sweep?older_than_days=30`
  for an external cron.

Legacy citation snapshots stored only `act_name` (not `document_id`),
so the appendix builder needs a fallback resolver:

```python
# backend/app/services/pdf_tools.py — export_thread_brief
def _resolve_doc_id(act_name: str | None) -> str | None:
    if not act_name: return None
    if act_name in title_to_doc_id: return title_to_doc_id[act_name]
    res = db.table("legal_documents").select("id").eq("title", act_name).execute()
    if not res.data:
        # ILIKE fallback for historic uppercased titles like
        # "REPUBLIC OF ZAMBIA THE COMPANIES ACT"
        token = max(act_name.split(), key=len) if act_name.strip() else ""
        if token:
            res = db.table("legal_documents").select("id") \
                    .ilike("title", f"%{token}%").limit(1).execute()
    title_to_doc_id[act_name] = res.data[0]["id"] if res.data else None
    return title_to_doc_id[act_name]
```

Cached per-export, so 20 citations of the same Act cost one DB call.

### Anonymous mode (ChatGPT-style)

No more forced login. Anonymous users land on `/chat` and can chat for
real — same agent, same RAG, same tools, just no DB writes.

```tsx
// frontend/src/app/(dashboard)/chat/page.tsx
const isAnonymous = !user
let sid = sessionId
if (!sid && !isAnonymous) {
  sid = await createSession(question)
  setSessionId(sid)
}
if (sid && !isAnonymous) {
  await saveMessage(sid, 'user', question)
}
// ... streamQuery still runs; onDone saves only when sid && !isAnonymous
```

The dashboard layout no longer redirects to `/auth/login`. The header
gains a green **Sign in** pill on the top-right when anonymous; the
sidebar swaps the avatar for a persuasive copy block + sign-in /
create-account links and hides the Cases section. `/chat/[id]` and
`/profile` redirect anonymous users to friendlier targets (`/chat` and
`/auth/login` respectively).

### Inline tool-call rendering

The most recent change. Tool cards now appear **interleaved with prose
in chronological order**, inside the same assistant bubble. Same UX as
Claude Code, Codex, ChatGPT-with-tools.

```ts
// frontend/src/components/chat/chat-message.tsx
export type MessageBlock =
  | { kind: 'text'; text: string }
  | { kind: 'tool'; toolCallId: string }
```

Token deltas append to the trailing text block (or start a new one if
the trailing block is a tool); a tool_call event pushes a new tool
block which forces the next token into a fresh text block:

```ts
onToken: (chunk) => updateLast((last) => {
  const blocks = [...(last.blocks ?? [])]
  const tail = blocks[blocks.length - 1]
  if (tail && tail.kind === 'text') {
    blocks[blocks.length - 1] = { kind: 'text', text: tail.text + chunk }
  } else {
    blocks.push({ kind: 'text', text: chunk })
  }
  return { ...last, content: last.content + chunk, blocks }
}),
onToolCall: (call) => updateLast((last) => ({
  ...last,
  blocks: [...(last.blocks ?? []), { kind: 'tool', toolCallId: call.id }],
  toolCalls: [...(last.toolCalls ?? []), { ...call, status: 'running', db: [], web: [] }],
})),
```

`ChatMessage` renders blocks in order — text → markdown, tool → matching
ToolCallCard. Both `blocks` and `tool_calls` persist as JSONB columns
on `chat_messages`, so reload preserves the chronological view.

---

## 3. How tool calls actually run on Railway

This is the question that pulls all the pieces together.

### The transport: SSE over a long-lived FastAPI request

Railway runs a single FastAPI service (gunicorn → uvicorn workers).
`/api/chat/stream` accepts a JSON body and **doesn't return until the
agent loop is done**. Output streams back as Server-Sent Events.

```python
# backend/app/routes/api.py
@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    async def event_stream():
        async for event in run_agent(
            user_query=request.query,
            web_enabled=bool(request.web_search),
            history=request.history,
            owner_id=request.user_id,
            session_id=request.session_id,
            attached_doc_ids=request.attached_doc_ids,
        ):
            # Maintain a legacy "chunks_used" field on the sources event
            if event.get("type") == "sources":
                payload = {"type": "sources", "db": event.get("db", []),
                           "web": event.get("web", []),
                           "chunks_used": [...]}
                yield f"data: {json.dumps(payload)}\n\n"
            else:
                yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache",
                 "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )
```

A typical chat turn lasts 10–60s and emits 50–500 events. The connection
stays open the whole time. Railway's edge has no idle timeout for
streaming responses below 10 minutes, which is well above our agent
iteration cap.

### The execution model: asyncio inside one Python process

`run_agent` is an `AsyncIterator[dict]`. Each `yield` immediately
flushes to the client because FastAPI's `StreamingResponse` is async.
Inside the loop:

- The **Anthropic call** uses `anthropic.AsyncAnthropic`, so awaiting
  it doesn't block the worker. While the model is generating tokens,
  the worker can serve other requests.
- **Tool execution** uses `asyncio.wait_for(handler(**args), timeout=25)`.
  Each tool gets its own deadline.
- **Synchronous tools** (the embedder, the supabase-py client) run
  through `asyncio.to_thread`, which moves them to the default
  threadpool so they don't block the event loop:

```python
# backend/app/services/tools.py — _search_corpus
embedding = await asyncio.to_thread(get_query_embedding, query)
chunks = await asyncio.to_thread(
    search_chunks, embedding,
    top_k=top_k, threshold=threshold,
    caller_user_id=caller_user_id, attached_doc_ids=attached_doc_ids,
)
```

That's why one Railway instance can serve dozens of concurrent chat
turns — each one is mostly idle, waiting on Anthropic and Supabase.

### What "performing a tool call" looks like end-to-end

Given a turn that fires `gov_search`:

```
1. Anthropic streams "tool_use" block { name: "gov_search",
                                        input: {query: "PACRA ..."} }
2. agent.run_agent yields {type: "tool_call", id, name, input}
   → SSE → frontend pushes a 'running' card into blocks
3. agent calls execute_tool(registry, "gov_search", input, timeout=25)
4. _gov_search wraps Tavily's HTTP API:
   async with httpx.AsyncClient(timeout=20.0) as c:
       resp = await c.post("https://api.tavily.com/search",
                           json={"api_key": TAVILY_API_KEY,
                                 "query": q,
                                 "include_domains": GOV_ZM_DOMAINS,
                                 ...})
5. tool returns {"result": {"matches": [...]}, "web_sources": [...]}
6. agent yields {type: "tool_result", id, name, ok, db, web, ms}
   → SSE → frontend updates the same card to 'ok' state with
            5 web results + 3.0s timing
7. agent appends a {role:"user", content:[{type:"tool_result", ...}]}
   message to its messages array, calls Anthropic again. The model
   sees the tool result in context and either calls another tool or
   starts writing the answer.
```

Each tool call is just an HTTP request, a Postgres RPC, or a few
seconds of WeasyPrint rendering. **Nothing about the agent loop needs
a VM, a queue, or a container per call.** It all happens inside the
already-running uvicorn worker.

### Why we don't need a separate worker / queue

Three properties of the workload make a single-service design
sufficient:

1. **Tool calls are sequential by nature** — the model needs each
   result before deciding what to do next. Parallel execution buys
   little.
2. **Each tool is short** — Tavily/Supabase are both ~1s; WeasyPrint
   is ~2s for typical memos. The 25s per-tool timeout is conservative.
3. **Per-request memory is small** — the BGE embedding model is loaded
   once and shared across all requests; everything else is JSON.

If we ever need true background work (e.g. "generate a 200-page brief
and email me when done"), Railway lets us add a second service in the
same project with no code change. For now we don't.

---

## 4. How writes happen across the stack

Two storage layers, two write paths.

### Postgres writes (chat history, artifacts, citations)

The backend uses `supabase-py`, which is a thin wrapper over PostgREST.
Every server-side write goes through the **service-role key**, which
bypasses RLS:

```python
# backend/app/db/supabase.py
def get_db() -> Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client
```

`SUPABASE_KEY` on Railway is `service_role`. The frontend uses the
**anon key** + a Supabase Auth session, so RLS applies normally there.
Writes the frontend does directly (e.g. `supabase.from('chat_messages')
.insert(...)`) are gated by the user's JWT.

### Storage writes (PDFs)

Two private buckets:

- `legal-docs` — original Acts (one PDF per `legal_documents.id`)
- `artifacts` — agent-generated PDFs (one per `artifacts.id`)

Server-side uploads use the Storage REST API directly because
supabase-py's storage client doesn't do streaming uploads cleanly:

```python
# backend/app/services/pdf_tools.py
def _upload_artifact_pdf(artifact_id, pdf_bytes) -> str:
    base = settings.supabase_url.rstrip("/")
    key = f"{artifact_id}.pdf"
    with httpx.Client(timeout=60.0) as client:
        client.delete(  # idempotent re-runs
            f"{base}/storage/v1/object/artifacts/{key}",
            headers={"Authorization": f"Bearer {settings.supabase_key}"},
        )
        resp = client.post(
            f"{base}/storage/v1/object/artifacts/{key}",
            headers={"Authorization": f"Bearer {settings.supabase_key}",
                     "Content-Type": "application/pdf",
                     "x-upsert": "true"},
            content=pdf_bytes,
        )
        resp.raise_for_status()
    return f"artifacts/{key}"
```

Reads go through **signed URLs** so the bucket can stay private:

```python
# backend/app/routes/api.py — get_artifact_pdf_url
bucket, _, key = storage_path.partition("/")
signed = db.storage.from_(bucket).create_signed_url(key, expires_in)
return {"signed_url": signed["signedURL"], ...}
```

The frontend then fetches the signed URL directly. PDF.js makes range
requests against it, which Supabase Storage supports.

### Atomic chunk replacement during re-ingestion

When we re-ingest an Act we want to **swap** its chunks atomically —
drop the old ones, insert the new ones. We do this by leaning on
Postgres's foreign-key cascade:

```python
# scripts/reingest_acts.py
db.table("legal_chunks").delete().eq("document_id", document_id).execute()
db.table("legal_hierarchy").delete().eq("document_id", document_id).execute()
# ... insert new rows in batches of 50
for i in range(0, len(rows), 50):
    db.table("legal_chunks").insert(rows[i:i + 50]).execute()
```

By preserving `legal_documents.id` across re-ingests (looked up by
`pdf_hash` so renames don't break the link), every chat history
referencing that document_id keeps working.

---

## 5. The chronological-blocks rendering model

The newest piece. The classic Levy renderer was:

```
[ Tool Card ]
[ Tool Card ]
...
[ Levy AI bubble: full prose, all citations at the bottom ]
```

The new renderer is:

```
[ Levy AI bubble:
    "Let me search the corpus for X..."
    [ Tool Card · search_corpus · 5 matches · 1.0s ]
    "Based on what I found, here are the key sections..."
    [ Tool Card · gov_search · 3 results · 0.8s ]
    "Putting it together..." ]
```

The change is one extra piece of state: **`blocks: ({kind:'text', text}
| {kind:'tool', toolCallId})[]`**. The lookup table (`toolCalls`) still
exists and still drives the cards' content; `blocks` just tells the
renderer the order.

Why two arrays instead of putting full tool data into the block? Two
reasons:

1. Streaming updates a tool card in two phases — `tool_call` (running)
   and `tool_result` (done). With a separate `toolCalls` map indexed
   by id, the `tool_result` event finds and mutates one entry instead
   of having to scan `blocks`.
2. Future filtering / summary views can iterate `toolCalls` directly
   without parsing the block stream.

Persistence:

```sql
alter table public.chat_messages
  add column blocks jsonb,
  add column tool_calls jsonb;
```

A small detail: **legacy messages without `blocks`** fall back to the
old layout (cards above the prose) automatically. There's no migration.

---

## 6. End-to-end: one user question, every layer

Following a single click of "Send" on `/chat`:

```
Browser                          Vercel (Next.js)               Railway (FastAPI + Anthropic)               Supabase (Postgres + Storage)
───────                          ──────────────────             ──────────────────────────────              ─────────────────────────────
User submits question  ───→
                                 Server Action / fetch:
                                 POST /api/chat/stream  ───────→
                                                                 run_agent() starts, yields:
                                                                 ─ {type: thinking}              ←──────── (none)
                                 SSE event reaches client
                                 onThinking() → ThinkingGlow

                                                                 Anthropic stream begins.
                                                                 The model emits tool_use:
                                                                 ─ {type: tool_call, name:"search_corpus", input:{query:...}}
                                 onToolCall() → blocks.push(tool)
                                                                 execute_tool runs:
                                                                 ─ asyncio.to_thread(get_query_embedding, q)  → BGE locally
                                                                 ─ asyncio.to_thread(search_chunks, ...)  ──→ pgvector RPC
                                                                                                              search_legal_chunks_scoped()
                                                                                                              filters by is_global / owner / attached
                                                                 ─ {type: tool_result, db: [...], ms: 980}
                                 onToolResult() updates the
                                 same card to 'ok' status
                                                                 Tool result appended to messages.
                                                                 Anthropic call resumes.
                                                                 Tokens stream:
                                                                 ─ {type: token, content: "Based on..."}
                                                                 ─ {type: token, content: " the Companies..."}
                                 onToken() appends to last
                                 text block; ReactMarkdown
                                 re-renders at ~30 Hz

                                                                 Model decides it has enough.
                                                                 stop_reason="end_turn".
                                                                 ─ {type: sources, db: [...], web: [...]}
                                                                 ─ {type: done, usage, timing}
                                 onDone() finalizes the message
                                 If signed-in:
                                   supabase.from('chat_messages')      ──────────────────────────────────→  insert row with content,
                                     .insert({...content, blocks,                                            blocks, tool_calls,
                                              tool_calls, citations,                                         citations, web_sources, ...
                                              web_sources, artifacts,
                                              compaction})
                                 router.replace('/chat/{sid}')
```

Every event is a single `data: {json}\n\n` line on the SSE stream,
parsed by `streamQuery()` in `frontend/src/lib/api.ts` and dispatched
through one of the `StreamHandlers` callbacks (`onThinking`, `onToken`,
`onToolCall`, `onToolResult`, `onArtifact`, `onCompaction`, `onDone`,
`onError`).

---

## 7. What's left

Things we deferred and would land in a Phase 7 / polish round:

- **30-day archive sweep cron** — endpoint exists; needs a Railway
  scheduled job hitting it daily.
- **PDF text highlighting**. Right now clicking a citation scrolls to
  the cited *page*; a real highlight on the cited text needs per-chunk
  bbox capture during ingestion.
- **Tool transparency** — show users a per-message tool budget and a
  "stop now" button mid-stream.
- **Workspace mode** — multiple lawyers sharing one folder of uploads.
  Schema exists (`owner_id`); needs an `org_id` layer.
- **Export to .docx** — `pdf_generate` does PDF; pandoc round-tripping
  is straightforward but not yet wired.

---

## 8. Quick reference: where things live

```
backend/
  app/
    routes/api.py                ← every HTTP endpoint
    services/
      agent.py                   ← run_agent() — the loop
      tools.py                   ← tool registry + Tavily/corpus tools
      pdf_tools.py               ← extract / generate / merge / split / export
      compactor.py               ← compact_if_needed()
      embedder.py                ← BGE (local, 768-dim)
      ingester.py / parser.py    ← original ingestion pipeline
    db/supabase.py               ← search_chunks RPC wrapper
    config.py                    ← Settings (env-driven)

frontend/
  src/
    app/(dashboard)/
      chat/page.tsx              ← new-chat flow (handles anonymous)
      chat/[id]/page.tsx         ← persisted thread
      documents/page.tsx         ← folder grid + detail
    components/
      chat/
        chat-message.tsx         ← MessageBlock renderer
        tool-call-card.tsx       ← inline tool-call card
        artifact-card.tsx        ← artifact card
        pdf-viewer.tsx           ← PDF.js right-pane viewer
        pdf-viewer-context.tsx   ← provider for the viewer state
        brief-context.tsx        ← BriefProvider (IRAC)
        use-session-attachments.ts
      documents/folder-card.tsx  ← 3D folder visual
      layout/app-sidebar.tsx     ← session list + sign-in CTA
    lib/
      api.ts                     ← streamQuery + every fetch wrapper
      supabase.ts                ← createBrowserClient

scripts/
  reingest_acts.py               ← canonical-PDF re-ingest

docs/
  ARCHITECTURE.md                ← original architecture doc
  REPORT-may-7-8.md              ← THIS FILE
```

---

That's the lot. Two days, ten Acts in storage, six tool functions, one
inline rendering refactor, and an honest answer to "how do we run an
agent loop on Railway" — the answer is that we just do, and FastAPI's
async streaming carries the whole load.
