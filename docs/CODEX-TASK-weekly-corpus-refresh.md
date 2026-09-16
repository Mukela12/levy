# Task: weekly corpus refresh (one command + a GitHub Action)

You are working in the Levy repo (github.com/Mukela12/levy, public). Levy is a
Zambian legal AI: FastAPI backend on Railway, Next.js frontend on Vercel,
Supabase for the corpus and vectors.

## Why this exists

Levy answers from a library of Zambian law stored in Supabase. That library is
a snapshot. Nothing currently tells it when the snapshot has gone stale, and
nothing goes looking for new law. A user already caught Levy answering from an
Act that Parliament repealed in 2022, because the library held the repealed Act
and the replacing Act side by side and retrieval cannot tell them apart.

That specific bug is fixed: there is now a law map (which Acts are repealed, by
what, and which amendments belong to which principal Act) that is attached to
every search result. But the map is only as current as the corpus, and the
corpus is only as current as the last time someone ran a harvest by hand.

Your job is to make the checking automatic. Not the ingesting. The checking.

## What to build

### 1. One command

A single entry point that a human can run locally:

```
scripts/refresh_corpus.sh
```

It must do exactly three things, in order, and print a readable summary:

1. **Diff Parliament against the library.** Run the existing dry run:
   `backend/.venv/bin/python scripts/harvest_parliament_acts.py --dry-run`
   This crawls parliament.gov.zm's Acts listing (about 1,030 entries), compares
   it against what Supabase holds, and prints one `would harvest ...` line per
   Act that is missing. It downloads no PDFs and calls no paid API.
2. **Rebuild the law map.**
   `backend/.venv/bin/python scripts/build_law_map.py --write`
   This reads repeal clauses out of the corpus and writes
   `backend/app/data/law_map.json`. Supabase reads only, no paid API.
3. **Write a report** to a path the workflow can pick up (your choice, keep it
   out of git or in a gitignored dir): how many Acts are missing, which ones,
   and the law map's status counts (in force / repealed / amending / bill /
   enacted) with the delta against the previous map.

Exit non-zero if either script fails. Never write a partial law map.

### 2. A weekly GitHub Action

`.github/workflows/corpus-refresh.yml`

- Schedule: once a week. Also `workflow_dispatch` so it can be run by hand.
- Ubuntu runner, Python 3.11.
- Install only what the scripts need. Do not install the full backend
  requirements if a smaller set works: the scripts need `supabase`, `httpx`,
  `python-dotenv` plus whatever `app.db.supabase` imports. Check before you
  guess.
- Run the same command as above.
- **Commit `backend/app/data/law_map.json` only when it actually changed.**
  The file carries a `generated_at` timestamp that changes on every run, so a
  naive `git diff --quiet` will commit every single week and trigger a pointless
  production deploy. Compare the `documents` and `unresolved` keys, ignoring
  `generated_at`.
- **Report the missing Acts as a GitHub issue.** One long-lived issue labelled
  `corpus-refresh`, updated in place each week, not a new issue every time.
  Look for an open issue with that label first; create it only if none exists.
  The issue body should list the Acts Parliament has that Levy does not, newest
  first, and the law map status counts.
- Needs `permissions: contents: write` and `issues: write`.
- Retry the Parliament crawl up to 3 times before failing. Their site times out
  regularly and a flaky night should not open a misleading issue saying 400 Acts
  are missing.

### 3. Repo secrets

The workflow needs exactly two, and the repo owner will add them (do not ask for
the values, do not print them, do not echo them into logs):

- `SUPABASE_URL`
- `SUPABASE_KEY`

Do not add an OpenAI key. See the constraints.

## Hard constraints

- **No ingesting in CI, ever.** Ingesting an Act embeds it, which spends money
  on the production OpenAI account. The standing rule in this project is that
  harvests never run on the production key. The weekly job detects and reports.
  A human ingests, on purpose, with a temporary key.
- **Official sources only.** parliament.gov.zm for Acts, judiciaryzambia.com for
  judgments. **Never scrape zambialii.org** and never touch the Zambia Law
  Reports. This is not negotiable and is not a performance question.
- **A push to `main` deploys production.** Railway rebuilds on `backend/**` and
  Vercel on the frontend. A bot commit of `law_map.json` therefore deploys the
  backend. That is acceptable and intended, which is exactly why the "only
  commit when changed" rule above matters.
- Never commit anything from `backend/.env`. Never print a secret.
- Do not change how the law map is built or how statuses are worded. That logic
  was tuned against real repeal clauses and a wrong "repealed" flag on a live Act
  is worse than no flag.

## Things already checked, so you do not have to

- `scripts/harvest_parliament_acts.py --dry-run` prints `would harvest <title>
  <act number>` per missing Act and ingests nothing. Confirmed by reading the
  code path at `main()`.
- `scripts/build_law_map.py --write` needs Supabase only, no embeddings.
- Both scripts do `load_dotenv(backend/.env)`, which silently does nothing when
  the file is absent. On a runner, plain environment variables work.
- Every field in `backend/app/config.py::Settings` defaults to an empty string,
  so `import app.db.supabase` succeeds with only `SUPABASE_URL` and
  `SUPABASE_KEY` set. Verified in a stripped environment.
- Local Python is 3.11.16 at `backend/.venv/bin/python`.
- **This repo is public, so Actions minutes are free and unlimited.** Do not
  disable or delete workflows in any other repo to "make room". The scrapers in
  `Mukela12/procura-intelligence` (17 active workflows) cost nothing either,
  because that repo is public too.
- GitHub disables scheduled workflows in a public repo after 60 days with no
  commits. The levy repo is active, but note it in a comment in the workflow so
  nobody is surprised later.

## Acceptance

- `scripts/refresh_corpus.sh` runs clean locally and prints the summary.
- The workflow runs green on `workflow_dispatch`.
- A run where the law map is unchanged produces **no commit**.
- A run where Acts are missing creates or updates exactly one issue.
- No secret appears in any log.

## Out of scope

Do not build ingestion, OCR, statutory instruments, or anything that writes to
Supabase. Those are separate jobs and they cost money. If the diff shows
statutory instruments are missing, that is expected: the library holds zero of
them today and fixing that is not this task.
