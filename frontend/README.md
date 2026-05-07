# Levy — Frontend

Next.js 16 (App Router, Turbopack) app for [Levy](../README.md). Deployed to Vercel at https://levy-ten.vercel.app.

## Stack

- **Next.js 16.2.1** with Turbopack
- **React 19**
- **Supabase Auth** via `@supabase/ssr` browser client
- **Tailwind CSS 4** + shadcn/ui + base-ui/react components
- **Framer Motion** for animations, **Lottie** for icon animation

## Routes

| Route                   | Purpose                                                |
|-------------------------|--------------------------------------------------------|
| `/`                     | Redirects to `/chat`                                   |
| `/auth/login`           | Email/password signin                                  |
| `/auth/signup`          | Account creation (sends confirmation email via Resend) |
| `/chat`                 | Chat with Levy (full RAG, streaming)                   |
| `/chat/[id]`            | Specific conversation                                  |
| `/search`               | Retrieval-only mode — preview chunks without LLM       |
| `/documents`            | Browse ingested Acts                                   |
| `/profile`              | User profile                                           |

`(dashboard)/layout.tsx` redirects unauthenticated users to `/auth/login`.

## Dev

```bash
npm install
cp .env.local.example .env.local   # fill in vars below
npm run dev                        # http://localhost:3000
```

### Environment

```
NEXT_PUBLIC_API_URL=https://levy-api-production.up.railway.app
NEXT_PUBLIC_SUPABASE_URL=https://zpdhoijcmotycbyelkbk.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon key>
```

For a local backend: `NEXT_PUBLIC_API_URL=http://localhost:8000`.

> **Heads-up:** `NEXT_PUBLIC_*` values are inlined into the JS bundle at build time. Make sure they have **no trailing whitespace or newlines** — a stray `\n` in the env value silently produces a `https://...supabase.co\n` URL in the deployed bundle, which fails DNS resolution. This bit us once already.

## Build & deploy

```bash
npm run build                      # Next.js production build
vercel deploy --prod --yes         # promote to levy-ten.vercel.app
```

## Key files

- [src/lib/supabase.ts](src/lib/supabase.ts) — `createBrowserClient` factory
- [src/lib/api.ts](src/lib/api.ts) — wraps the FastAPI backend (chat, search, stream, brief)
- [src/components/auth/auth-provider.tsx](src/components/auth/auth-provider.tsx) — session context (`useAuth`)
- [src/app/(dashboard)/layout.tsx](src/app/(dashboard)/layout.tsx) — auth gate + sidebar shell

## Note on Next.js 16

This codebase uses Next.js 16 with breaking changes from earlier versions. See [AGENTS.md](AGENTS.md) before making structural changes.
