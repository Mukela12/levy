# Levy — AI Legal Assistant for Zambia

Ask questions about Zambian law and get answers grounded in actual legislation, with citations to specific Acts, sections, and pages.

- **Live:** https://levy-ten.vercel.app
- **API:** https://levy-api-production.up.railway.app

## Architecture

```
┌─────────────────────────┐      ┌───────────────────────────┐      ┌─────────────────────────┐
│  Next.js 16 (App Router)│      │  FastAPI (Python 3.12)    │      │  Supabase Postgres      │
│  Vercel — levy-ten      │ ───▶ │  Railway — levy-api       │ ───▶ │  + pgvector (HNSW, 768) │
│  @supabase/ssr auth     │      │  RAG: embed → search → LLM│      │  3,882 chunks · 12 Acts │
└─────────────────────────┘      └───────────────────────────┘      └─────────────────────────┘
            │                              │                                    │
            │                              ▼                                    │
            │                  ┌───────────────────────┐                        │
            │                  │  Anthropic Claude     │                        │
            │                  │  claude-sonnet-4      │                        │
            │                  └───────────────────────┘                        │
            ▼                                                                   ▼
┌─────────────────────────┐                                       ┌─────────────────────────┐
│  Supabase Auth          │                                       │  BGE-base-en-v1.5       │
│  + Resend SMTP          │                                       │  (sentence-transformers,│
│  no-reply@degreedesk.app│                                       │   embedded in API image)│
└─────────────────────────┘                                       └─────────────────────────┘
```

## Repo layout

```
backend/      FastAPI service — RAG pipeline, deployed to Railway
frontend/     Next.js 16 app — deployed to Vercel
supabase/     SQL migrations (pgvector schema, 768-dim chunks, search RPC)
scripts/      One-off ingestion / DB-setup / CLI ask scripts
docs/         ARCHITECTURE.md — RAG strategy & evolution timeline
```

## API endpoints

| Method | Path                       | Purpose                                                   |
|--------|----------------------------|-----------------------------------------------------------|
| GET    | `/health`                  | Liveness check                                            |
| POST   | `/api/chat`                | Full RAG: embed → retrieve → generate with citations      |
| POST   | `/api/chat/stream`         | Same, server-sent events                                  |
| POST   | `/api/search`              | Retrieval only (no LLM) — for evaluating retrieval quality|
| GET    | `/api/documents`           | List ingested Acts and chunk counts                       |
| POST   | `/api/documents/upload`    | Ingest a new PDF (parse → chunk → embed → store)          |
| POST   | `/api/brief/generate`      | IRAC brief from a conversation                            |

## Local development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

Required env (`backend/.env`):

```
SUPABASE_URL=https://zpdhoijcmotycbyelkbk.supabase.co
SUPABASE_KEY=<anon key>
ANTHROPIC_API_KEY=sk-ant-...
EMBEDDING_PROVIDER=local       # uses BAAI/bge-base-en-v1.5 (768-dim)
EMBEDDING_DIMENSIONS=768
RETRIEVAL_TOP_K=5
SIMILARITY_THRESHOLD=0.6
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local     # see below
npm run dev                    # http://localhost:3000
```

Required env (`frontend/.env.local`):

```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://zpdhoijcmotycbyelkbk.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon key>
```

## Deploy

| Component | Tool             | Command                                              |
|-----------|------------------|------------------------------------------------------|
| Backend   | Railway CLI      | `cd backend && railway up --service levy-api`        |
| Frontend  | Vercel CLI       | `cd frontend && vercel deploy --prod --yes`          |
| DB schema | Supabase Mgmt API| Apply files in `supabase/migrations/`                |

The Railway image bakes the BGE-base model (`~440MB`) into the image at build time so the first request doesn't pay model-load latency. Build uses CPU-only torch (`+cpu` index) — full CUDA torch is ~5GB and unnecessary on Railway's CPU runners.

## Auth flow

Signup uses Supabase Auth (`@supabase/ssr` browser client). Confirmation emails go through Resend SMTP (`smtp.resend.com:465`, sender `Levy <no-reply@degreedesk.app>`). After clicking the confirmation link the user lands on `https://levy-ten.vercel.app` with the session in the URL hash; `AuthProvider` picks it up via `onAuthStateChange` and the user is redirected into `/chat` by the dashboard layout.

A `public.profiles` row is auto-created on signup via the `handle_new_user` trigger on `auth.users`.

## Embedding model

Chunks were ingested with `BAAI/bge-base-en-v1.5` (768-dim). The DB column is `vector(768)` with an HNSW cosine index. **Switching providers requires re-ingesting the corpus** — vectors from different models aren't comparable. The original Voyage `voyage-law-2` (1024-dim) path is still in [backend/app/services/embedder.py](backend/app/services/embedder.py:1) but disabled by default.

## What's ingested

12 Acts, 3,882 chunks, 4,300+ sections — Constitution, Penal Code, Companies Act, Employment Code, Mines & Minerals Development Act, Environmental Management Act, Public Procurement Act, Lands Act, Lands & Deeds Registry Act, Government of Zambia Act, and others.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — RAG strategy, chunking decisions, evaluation approach, and the broader RAG evolution timeline.
