# Levy — Security Review & Hardening (May 2026)

A security researcher (Reddit: m_matongo) reported he could, in ~20 minutes,
read every user's data, enumerate all users, and delete/rename anyone's
documents and folders. **The findings were accurate.** This document records
what was wrong, what caused it, what we fixed, and how to avoid the whole
class of bug on future projects.

---

## 1. What was exposed

All of it traced to **broken access control** — the #1 item on the OWASP Top
10. Concretely:

- **Read any user's data.** The browser app queried Supabase directly with
  the public `anon` key, and **no table had Row-Level Security (RLS)**. So
  anyone could take the anon key (it ships in every browser bundle) and hit
  `https://<project>.supabase.co/rest/v1/chat_messages?select=*` to dump
  every user's chats, or enumerate `chat_sessions` to list all users.
- **Delete / rename anyone's data.** Same path allowed `DELETE` and
  `UPDATE`, and separately the **backend trusted a client-supplied
  `user_id`** on every endpoint — e.g. `PATCH /api/folders/{id}` renamed a
  folder by id with no ownership check; `GET /api/documents?user_id=<victim>`
  returned the victim's documents.
- **"Sessions aren't concrete."** There was no server-side identity at all —
  the API believed whatever `user_id` the client sent.
- **A public destructive endpoint.** `POST /api/artifacts/sweep?dry_run=false`
  deleted stored files and was callable by anyone.

---

## 2. Root causes (the "why")

Three compounding mistakes, none exotic:

1. **RLS was never enabled.** Supabase ships with RLS *off* by default; you
   must turn it on per table and write policies. We never did, so the
   database had no opinion about who could touch which row.
2. **The anon key was treated as a secret it isn't — and the real backstop
   (RLS) was missing.** The anon key is *designed* to be public. It is only
   safe **because** RLS is supposed to constrain it. With RLS off, the
   "public" key became a master key.
3. **The backend authenticated nothing.** It ran on the `service_role` key
   (which *bypasses* RLS by design) and trusted client-supplied identifiers.
   A service-role backend MUST authorize every request in code; ours didn't.

The underlying theme: **identity and authorization were assumed, never
verified.** The app trusted the client to say who it was and what it owned.

---

## 3. What we fixed

**A. Row-Level Security on every user table** (`20260525000000_rls_security.sql`)
- `chat_sessions`, `chat_messages`, `chat_session_documents`,
  `document_folders`, `template_folders`, `templates`, `artifacts`,
  `legal_documents`/`legal_chunks`/`legal_hierarchy`.
- Policies key off `auth.uid()` — a user sees/edits only their own rows.
  Global library rows (`is_global = true`) stay public-read.
- Verified: with the public anon key, `chat_messages`/`chat_sessions` now
  return `[]`; the global library still reads.

**B. Backend authentication + ownership checks** (`app/auth.py`, `routes/api.py`)
- Every owner-scoped endpoint now derives the user id from the **verified
  Supabase access token** (checked via GoTrue `/auth/v1/user`, 60s cache) and
  **ignores any client-supplied `user_id`**.
- Mutations assert row ownership: renaming/deleting another user's
  folder/template/session → `403`; missing → `404` (was a silent `200`).
- Signed-URL endpoints: global docs public, user docs owner-only; artifacts
  owner-only.
- `/artifacts/sweep` gated behind an `ADMIN_API_TOKEN` header.

**C. Frontend sends the token** (`lib/api.ts`)
- An `authHeaders()` helper attaches `Authorization: Bearer <token>` (read
  from the live Supabase session) to every owner-scoped API call.

**Defense in depth:** even if one layer is misconfigured later, the other
still holds — RLS guards the direct-DB path, backend auth guards the API path.

---

## 4. How to think about security on every new project

A short checklist that would have caught all of this on day one:

1. **Decide the trust boundary first.** Everything the browser holds is
   public — keys in `NEXT_PUBLIC_*`, anything in the JS bundle, any request
   the client makes. Assume an attacker has your anon key and can craft any
   API request. Design as if the client is hostile.
2. **Authorize on the server, never trust client-supplied identity.** Derive
   "who is this?" from a verified token (or session), never from a `user_id`
   in the body/query. Then check "do they own this row?" on every read and
   mutation.
3. **Turn on RLS the moment you create a Supabase table.** Default-deny, then
   add `auth.uid()` policies. Treat a table without RLS as a public table.
4. **Know which key bypasses what.** `anon` = constrained by RLS (browser-
   safe *iff* RLS is on). `service_role` = bypasses RLS (server-only; if you
   use it, you own authorization in code).
5. **Default-deny, then open up.** Start with no access and grant the minimum
   each feature needs — the opposite of "it works, ship it."
6. **Protect destructive + admin actions explicitly** (delete, sweep, bulk
   ops): require auth + ownership, and keep cron/admin endpoints behind a
   secret.
7. **Test the negative path.** For every "can a user do X to their data?"
   write "can a *different* user do X to it?" — and confirm it's blocked.
8. **Get a second set of eyes.** A 20-minute external look found all of this.
   Invite it early; reward the people who report it.

Mnemonic: **AuthN before AuthZ before action** — verify *who* they are, check
*what* they may touch, *then* do it.

---

## 5. Would TanStack Query have helped? (and the anon-key question)

Short answer: **No — TanStack Query is not a security tool, and it would not
have prevented this.** But the architecture question underneath it is a good
one. Let's separate the two.

### What TanStack Query actually is
It's a **client-side data-fetching and caching** library. You hand it a fetch
function; it dedupes, caches, retries, and tracks loading/error state. It has
**no opinion about where data comes from or what credentials are used** — it
just calls whatever you give it. So adding it changes nothing about exposure.

### The real question: should the client talk to Supabase directly, or go
through your backend?

There are two legitimate architectures:

**Model A — Client → Supabase directly (anon key + RLS).**
This is Supabase's intended design. The anon key is *meant* to be public; RLS
is the security layer. *This is what Levy uses now, and after enabling RLS it
is secure.* The bug was never "we exposed the anon key" — it was "we exposed
the anon key **without RLS**."

**Model B — Client → your backend API → Supabase (service_role, server-side).**
The browser never queries Supabase data tables directly; it calls your API,
which holds `service_role` server-side and authorizes each request. This is
where TanStack Query fits naturally — you'd use it to call *your* endpoints
(the ones we just locked down with JWT auth).

### Does Model B let you stop exposing the anon key?
**Almost, but not entirely** — and it doesn't remove the need for the other
controls:

- You would no longer need the anon key for **data queries** (those go
  through your API). ✅
- But you **still need the anon key in the browser for Supabase *Auth*** —
  sign-in, session storage, and token refresh all run client-side with the
  anon key. There's no way around that while using Supabase Auth. So the key
  stays public; it just does less.
- You would still want **RLS on** as a backstop (defense in depth), because
  the anon key remains reachable.
- And you would still need **server-side authorization** — Model B doesn't
  give you that for free; it's exactly the JWT + ownership checks we added.

### Bottom line
- TanStack Query: **adopt it for DX** (caching, dedupe, loading states) if you
  like — it's genuinely nice. It is **not** a security control.
- The anon key being public is **fine by design**; the fix was **RLS**, not
  hiding the key.
- Routing all data through your backend (Model B) is a reasonable hardening
  choice and pairs well with TanStack Query, **but** you can't fully remove
  the anon key (Auth needs it), you should keep RLS on regardless, and the
  security still comes from **server-side auth + RLS**, not from the fetching
  library.

For Levy specifically: we kept Model A for chat history (direct + RLS) and
Model B for documents/templates/folders (your API + JWT). Both are now
locked down. If you later want a single consistent model, moving the chat
reads behind the backend API + TanStack Query is a fine refactor — just keep
RLS enabled either way.
