# Levy ops scripts

Corpus ingestion, data pulls, QA and benchmarks. All read-only unless the name
says otherwise (`ingest_*`, `fix_*`, `dedupe_*` write to the database).

## Running them

Use the backend virtualenv and run from `backend/`:

```bash
cd ~/levy/backend
.venv/bin/python ../scripts/qa_changes.py
.venv/bin/python ../scripts/watch_feedback.py 7
```

The scripts resolve the repo root from their own location and load
`backend/.env` from that checkout — so a checkout without a `.env` fails with
`SupabaseException: supabase_url is required`. That is a missing config file,
not a broken venv.

## First-time setup

```bash
cd ~/levy/backend
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

**On macOS that install fails**, and the error is misleading:

```
ERROR: Could not find a version that satisfies the requirement torch==2.4.1+cpu
```

`requirements.txt` pins `torch==2.4.1+cpu` for the Linux production image;
`+cpu` wheels are not published for macOS/ARM. pip resolves everything before
installing anything, so this one line aborts the whole install and you end up
with an empty venv rather than a partial one.

Locally you do not need it: `torch` and `sentence-transformers` exist only for
`EMBEDDING_PROVIDER=local`, and Levy runs `openai`. Install the rest:

```bash
grep -vE '^(torch|sentence-transformers)==|^--extra-index-url' requirements.txt > /tmp/req-local.txt
.venv/bin/python -m pip install -r /tmp/req-local.txt wordninja
```

`wordninja` is used by some ingest scripts and is not pinned in
`requirements.txt`.

## The ones worth knowing

| Script | What it does |
| --- | --- |
| `watch_feedback.py [days]` | Answer feedback sliced by the model that produced it, plus the anonymous funnel. This is how the Haiku-vs-Sonnet question gets settled. Thumbs-down **reasons** are printed in full here and deliberately nowhere else. |
| `qa_changes.py` | Asserts behaviour of the current change set — matter tools, entitlement law, date parsing, the Kimi fallback wiring, retryable-error handling. |
| `qa_production.py` | Hits the **live** deploy: health monitors, auth gates, anonymous-chat refusals, deployed frontend bundle. |
| `bench_kimi_vs_claude.py` | Cost and tool-choice benchmark on Levy's real system prompt and all 27 tools. Needs `MOONSHOT_API_KEY`. |
| `who_is_user.py <email>` | Everything one user asked, for field-study work. |

## Gotchas

- **Import `_dns_resilient` first** in anything that talks to Supabase. The dev
  Mac has flaky `getaddrinfo` that intermittently fails for hosted services.
- **Never run these from the repo root.** `supabase/` (the migrations
  directory) shadows the `supabase` Python package on `sys.path`, and the
  import fails with a confusing `ModuleNotFoundError`. Run from `backend/`.
- **Never scrape zambialii.org, and never ingest the Zambia Law Reports.**
  Source only from official government sites (judiciaryzambia.com,
  parliament.gov.zm, and similar).
