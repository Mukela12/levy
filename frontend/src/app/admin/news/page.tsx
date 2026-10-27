'use client'

/**
 * Levy News review, shadow mode. The editor reads each check the daily run
 * made and approves, holds or rejects it. Nothing here is published: the
 * decisions build the accuracy record that decides when Levy News can go live.
 * Backend: backend/app/routes/news_admin.py, behind the ADMIN_API_TOKEN secret.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const TOKEN_KEY = 'levy-admin-token'
const STATUSES = ['pending', 'held', 'approved', 'rejected'] as const
type Status = (typeof STATUSES)[number]
type Label = 'True' | 'Misleading' | 'False' | 'Unproven'

interface Source {
  url: string
  publisher: string
  date: string
  source_type: string
  quote: string
  stance: 'supports' | 'contradicts' | 'neutral'
  quote_found: boolean | null
}

interface CoverageItem {
  outlet: string
  outlet_type: string
  title: string
  url: string
  published_at: string | null
}

interface Check {
  id: string
  story_id: string
  label: Label
  confidence: number | null
  headline: string | null
  claim: string
  verdict_text: string | null
  what_we_found: string | null
  case_for: string[]
  case_against: string[]
  would_change: string | null
  evidence: Source[]
  evidence_summary: string | null
  flags: string[]
  review_status: Status
  review_note: string | null
  reviewed_at: string | null
  recheck_at: string | null
  cost_usd: number | null
  created_at: string
  news_stories: { title: string; category: string | null; outlet_count: number; social_count: number; first_seen_at: string } | null
  coverage: CoverageItem[]
}

interface Run {
  id: string
  started_at: string
  finished_at: string | null
  items_new: number
  stories_new: number
  checks_made: number
  cost_usd: number
  note: string | null
}

const LABEL_STYLE: Record<Label, string> = {
  True: 'bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-950 dark:text-emerald-200 dark:ring-emerald-900',
  Misleading: 'bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-950 dark:text-amber-200 dark:ring-amber-900',
  False: 'bg-red-50 text-red-800 ring-red-200 dark:bg-red-950 dark:text-red-200 dark:ring-red-900',
  Unproven: 'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:ring-slate-700',
}
const LABEL_MARK: Record<Label, string> = { True: '✓', Misleading: '!', False: '✕', Unproven: '?' }

const OWNERSHIP: Record<string, string> = {
  state: 'State-owned', private: 'Private', social: 'Social media', official: 'Official',
  aggregator: 'Aggregator', fact_checker: 'Fact-checker',
}

/** Plain words for each flag the pipeline sets (backend: services/news/verify.py apply_guards). */
function explainFlag(flag: string): string {
  if (flag.startsWith('quote_not_found:')) {
    const nums = flag.split(':')[1]
    return `Quote ${nums.split(',').join(', ')} wasn't found on its page. Check it before trusting it.`
  }
  const text: Record<string, string> = {
    'risk:named_person': 'Names a person. Their side is needed before this could be published.',
    'risk:election': 'About an election. Rely only on what the ECZ declared and primary documents.',
    'risk:court_case': 'About a case before a court. Report only filings and what was said in open court.',
    'risk:health': 'A health claim. Check it against the Ministry of Health or ZNPHI.',
    'risk:violence': 'About violence or unrest.',
    'risk:ethnicity': 'Touches on tribe or region. Never repeat slurs.',
    right_of_reply: 'Ask the person named for a reply first.',
    recent_no_contradiction: 'Under 48 hours old with nothing contradicting it, so it was set to Unproven. A re-check is due.',
    no_evidence: 'No sources were found.',
  }
  return text[flag] ?? flag
}

function ago(iso: string | null): string {
  if (!iso) return ''
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (mins < 60) return `${Math.max(1, mins)} min ago`
  const hours = Math.round(mins / 60)
  if (hours < 48) return `${hours} h ago`
  return `${Math.round(hours / 24)} days ago`
}

function readToken(): string {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export default function NewsReviewPage() {
  const [token, setToken] = useState('')
  const [draftToken, setDraftToken] = useState('')
  const [status, setStatus] = useState<Status>('pending')
  const [checks, setChecks] = useState<Check[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [runs, setRuns] = useState<Run[]>([])
  const [running, setRunning] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmRun, setConfirmRun] = useState(false)

  useEffect(() => setToken(readToken()), [])

  const call = useCallback(async (path: string, init?: RequestInit) => {
    const res = await fetch(`${API_URL}/api/admin/news${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', 'X-Admin-Token': token, ...(init?.headers || {}) },
    })
    if (res.status === 403) {
      try { sessionStorage.removeItem(TOKEN_KEY) } catch { /* storage blocked */ }
      setToken('')
      throw new Error('That admin token was refused.')
    }
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Request failed (${res.status})`)
    return res.json()
  }, [token])

  const load = useCallback(async () => {
    if (!token) return
    setError('')
    try {
      const [c, r] = await Promise.all([call(`/checks?status=${status}`), call('/runs?limit=5')])
      setChecks(c.checks)
      setCounts(c.counts)
      setRuns(r.runs)
      setRunning(r.running)
      setSelectedId((id) => (c.checks.some((x: Check) => x.id === id) ? id : null))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load checks.')
    }
  }, [call, status, token])

  useEffect(() => { void load() }, [load])

  const selected = useMemo(() => checks.find((c) => c.id === selectedId) ?? null, [checks, selectedId])
  useEffect(() => setNote(selected?.review_note ?? ''), [selected])

  async function decide(action: 'approve' | 'hold' | 'reject' | 'reopen') {
    if (!selected) return
    setBusy(true)
    try {
      await call(`/checks/${selected.id}/review`, { method: 'POST', body: JSON.stringify({ action, note }) })
      const index = checks.findIndex((c) => c.id === selected.id)
      const next = checks[index + 1] ?? checks[index - 1] ?? null
      await load()
      setSelectedId(next?.id ?? null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save the decision.')
    } finally {
      setBusy(false)
    }
  }

  async function runNow() {
    setConfirmRun(false)
    try {
      await call('/run?max_checks=3&budget_usd=0.5', { method: 'POST' })
      setRunning(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start a run.')
    }
  }

  if (!token) {
    return (
      <main className="min-h-dvh bg-stone-50 px-4 py-16 text-stone-900 dark:bg-stone-950 dark:text-stone-100">
        <form
          className="mx-auto grid max-w-sm gap-4"
          onSubmit={(e) => {
            e.preventDefault()
            try { sessionStorage.setItem(TOKEN_KEY, draftToken.trim()) } catch { /* storage blocked */ }
            setToken(draftToken.trim())
          }}
        >
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-800 dark:text-emerald-300">Levy editor</p>
          <h1 className="font-[family-name:var(--font-news)] text-3xl font-semibold">Levy News review</h1>
          <label htmlFor="admin-token" className="text-sm text-stone-600 dark:text-stone-400">Admin token</label>
          <input
            id="admin-token"
            type="password"
            autoComplete="off"
            value={draftToken}
            onChange={(e) => setDraftToken(e.target.value)}
            className="h-11 rounded-xl border border-stone-300 bg-white px-3 text-base outline-none focus:border-emerald-700 dark:border-stone-700 dark:bg-stone-900"
          />
          <button type="submit" disabled={!draftToken.trim()} className="h-11 rounded-xl bg-stone-900 font-semibold text-white disabled:opacity-40 dark:bg-stone-100 dark:text-stone-900">
            Open the review queue
          </button>
          {error && <p className="text-sm text-red-700 dark:text-red-300">{error}</p>}
          <p className="text-xs text-stone-500">Kept for this browser tab only.</p>
        </form>
      </main>
    )
  }

  const lastRun = runs[0]

  return (
    <main className="min-h-dvh bg-stone-50 text-stone-900 dark:bg-stone-950 dark:text-stone-100">
      <header className="border-b border-stone-200 bg-white/80 px-4 py-4 backdrop-blur dark:border-stone-800 dark:bg-stone-900/80">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-800 dark:text-emerald-300">Shadow mode · nothing here is published</p>
            <h1 className="font-[family-name:var(--font-news)] text-2xl font-semibold">Levy News review</h1>
            {lastRun && (
              <p className="mt-1 text-sm text-stone-500">
                Last run {ago(lastRun.started_at)}: {lastRun.items_new} new headlines, {lastRun.checks_made} checks, ${Number(lastRun.cost_usd).toFixed(2)}
                {lastRun.note ? ` · ${lastRun.note}` : ''}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            {running ? (
              <span className="rounded-full bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">A run is in progress</span>
            ) : confirmRun ? (
              <>
                <span className="text-sm text-stone-600 dark:text-stone-400">Up to 3 checks, about $0.30</span>
                <button onClick={runNow} className="h-9 rounded-lg bg-stone-900 px-3 text-sm font-semibold text-white dark:bg-stone-100 dark:text-stone-900">Start</button>
                <button onClick={() => setConfirmRun(false)} className="h-9 rounded-lg px-3 text-sm">Cancel</button>
              </>
            ) : (
              <button onClick={() => setConfirmRun(true)} className="h-9 rounded-lg border border-stone-300 px-3 text-sm font-semibold dark:border-stone-700">Run now</button>
            )}
            <button onClick={() => void load()} className="h-9 rounded-lg px-3 text-sm text-stone-600 dark:text-stone-400">Refresh</button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-4 py-4">
        <nav className="flex gap-1 overflow-x-auto rounded-xl bg-stone-100 p-1 dark:bg-stone-900" aria-label="Review status">
          {STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => { setStatus(s); setSelectedId(null) }}
              aria-pressed={status === s}
              className={`h-9 flex-1 whitespace-nowrap rounded-lg px-3 text-sm font-semibold capitalize ${status === s ? 'bg-white shadow-sm dark:bg-stone-800' : 'text-stone-500'}`}
            >
              {s} <span className="tabular-nums text-stone-400">{counts[s] ?? 0}</span>
            </button>
          ))}
        </nav>
        {error && <p role="alert" className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">{error}</p>}

        <div className="mt-4 grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
          <ul className={`grid content-start gap-2 ${selected ? 'hidden lg:grid' : ''}`}>
            {checks.length === 0 && (
              <li className="rounded-2xl border border-dashed border-stone-300 p-6 text-sm text-stone-500 dark:border-stone-700">
                No {status} checks. The next run will add stories here.
              </li>
            )}
            {checks.map((c) => (
              <li key={c.id}>
                <button
                  onClick={() => setSelectedId(c.id)}
                  className={`grid w-full gap-2 rounded-2xl border bg-white p-4 text-left dark:bg-stone-900 ${c.id === selectedId ? 'border-emerald-700 ring-2 ring-emerald-700/15' : 'border-stone-200 hover:border-stone-300 dark:border-stone-800'}`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold ring-1 ${LABEL_STYLE[c.label]}`}>
                      <span aria-hidden>{LABEL_MARK[c.label]}</span>{c.label}
                    </span>
                    <span className="text-xs text-stone-500">{ago(c.created_at)}</span>
                  </span>
                  <span className="font-[family-name:var(--font-news)] text-[17px] font-semibold leading-snug">{c.headline || c.claim}</span>
                  <span className="text-xs text-stone-500">
                    {(() => { const n = c.news_stories?.outlet_count ?? c.coverage.length; return `${n} outlet${n === 1 ? '' : 's'}` })()}
                    {c.news_stories?.social_count ? ` · ${c.news_stories.social_count} social` : ''}
                    {c.flags.length ? ` · ${c.flags.length} flag${c.flags.length > 1 ? 's' : ''}` : ''}
                  </span>
                </button>
              </li>
            ))}
          </ul>

          {selected ? (
            <CheckDetail
              check={selected}
              note={note}
              setNote={setNote}
              busy={busy}
              onDecide={decide}
              onBack={() => setSelectedId(null)}
            />
          ) : (
            <div className="hidden rounded-2xl border border-dashed border-stone-300 p-10 text-center text-sm text-stone-500 lg:block dark:border-stone-700">
              Choose a check to read it.
            </div>
          )}
        </div>
      </div>
    </main>
  )
}

function CheckDetail({ check, note, setNote, busy, onDecide, onBack }: {
  check: Check
  note: string
  setNote: (v: string) => void
  busy: boolean
  onDecide: (a: 'approve' | 'hold' | 'reject' | 'reopen') => void
  onBack: () => void
}) {
  const paragraphs = (check.what_we_found || '').split(/\n\s*\n/).filter(Boolean)
  return (
    <article className="min-w-0 rounded-2xl border border-stone-200 bg-white p-5 sm:p-7 dark:border-stone-800 dark:bg-stone-900">
      <button onClick={onBack} className="mb-4 text-sm font-semibold text-emerald-800 lg:hidden dark:text-emerald-300">‹ All checks</button>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-bold ring-1 ${LABEL_STYLE[check.label]}`}>
          <span aria-hidden>{LABEL_MARK[check.label]}</span>{check.label}
        </span>
        {check.confidence !== null && (
          <span className="text-xs text-stone-500" title="The model's own estimate. Not shown to readers until it is calibrated.">
            model confidence {check.confidence}%
          </span>
        )}
        {check.news_stories?.category && <span className="text-xs uppercase tracking-wider text-stone-400">{check.news_stories.category.replace('_', ' ')}</span>}
      </div>
      <h2 className="mt-3 font-[family-name:var(--font-news)] text-[28px] font-semibold leading-tight text-balance">{check.headline || check.claim}</h2>

      <div className="mt-4 rounded-xl border border-dashed border-stone-300 p-3 dark:border-stone-700">
        <p className="text-[11px] font-bold uppercase tracking-[0.13em] text-stone-500">What was claimed</p>
        <p className="mt-1 font-[family-name:var(--font-news)] text-[17px] italic leading-relaxed">{check.claim}</p>
        {check.news_stories && <p className="mt-1 text-xs text-stone-500">First seen {ago(check.news_stories.first_seen_at)}</p>}
      </div>

      {check.verdict_text && <p className="mt-4 font-[family-name:var(--font-news)] text-[18px] leading-relaxed">{check.verdict_text}</p>}

      {check.flags.length > 0 && (
        <ul className="mt-4 grid gap-1.5">
          {check.flags.map((f) => (
            <li key={f} className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">{explainFlag(f)}</li>
          ))}
        </ul>
      )}

      {paragraphs.length > 0 && (
        <section className="mt-6">
          <h3 className="text-[11px] font-bold uppercase tracking-[0.14em] text-emerald-800 dark:text-emerald-300">What we found</h3>
          <div className="mt-2 grid gap-3 font-[family-name:var(--font-news)] text-[17px] leading-[1.65] text-stone-800 dark:text-stone-200">
            {paragraphs.map((p, i) => (
              <p key={i}>
                {p.split(/(\[\d+\])/g).map((part, j) => {
                  const m = part.match(/^\[(\d+)\]$/)
                  return m ? (
                    <a key={j} href={`#src-${check.id}-${m[1]}`} className="mx-0.5 inline-grid h-5 min-w-5 place-items-center rounded-full border border-stone-300 px-1 align-[0.2em] font-sans text-[11px] font-bold text-emerald-800 no-underline dark:border-stone-700 dark:text-emerald-300">{m[1]}</a>
                  ) : <span key={j}>{part}</span>
                })}
              </p>
            ))}
          </div>
        </section>
      )}

      {(check.case_for.length > 0 || check.case_against.length > 0) && (
        <section className="mt-6 grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl bg-stone-50 p-4 dark:bg-stone-800/60">
            <h3 className="font-[family-name:var(--font-news)] text-lg font-semibold">The case for</h3>
            <ul className="mt-2 grid list-disc gap-1.5 pl-5 text-sm leading-relaxed">{check.case_for.map((x, i) => <li key={i}>{x}</li>)}</ul>
          </div>
          <div className="rounded-xl bg-stone-50 p-4 dark:bg-stone-800/60">
            <h3 className="font-[family-name:var(--font-news)] text-lg font-semibold">The case against</h3>
            <ul className="mt-2 grid list-disc gap-1.5 pl-5 text-sm leading-relaxed">{check.case_against.map((x, i) => <li key={i}>{x}</li>)}</ul>
          </div>
        </section>
      )}
      {check.would_change && (
        <p className="mt-3 rounded-xl bg-emerald-50 px-4 py-3 text-sm leading-relaxed text-emerald-950 dark:bg-emerald-950 dark:text-emerald-100">
          <b>What would change the verdict:</b> {check.would_change}
        </p>
      )}

      <section className="mt-6">
        <h3 className="text-[11px] font-bold uppercase tracking-[0.14em] text-emerald-800 dark:text-emerald-300">Sources ({check.evidence.length})</h3>
        <ol className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-2">
          {check.evidence.map((s, i) => (
            <li key={i} id={`src-${check.id}-${i + 1}`} className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-1.5 rounded-xl border border-stone-200 p-3 dark:border-stone-800">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="grid h-5 w-5 place-items-center rounded-full bg-stone-900 font-bold text-white dark:bg-stone-100 dark:text-stone-900">{i + 1}</span>
                <span className="font-semibold">{s.publisher}</span>
                <span className="text-stone-500">{s.date}</span>
                <span className="rounded-full bg-stone-100 px-2 py-0.5 font-semibold uppercase tracking-wider text-stone-600 dark:bg-stone-800 dark:text-stone-300">{s.source_type}</span>
                <span className={`rounded-full px-2 py-0.5 font-semibold ${s.stance === 'contradicts' ? 'bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200' : s.stance === 'supports' ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200' : 'bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300'}`}>{s.stance}</span>
              </div>
              <p className="border-l-2 border-stone-200 pl-3 font-[family-name:var(--font-news)] text-[15.5px] italic leading-relaxed dark:border-stone-700">{s.quote}</p>
              <div className="flex min-w-0 flex-wrap items-center gap-3 text-xs">
                <a href={s.url} target="_blank" rel="noreferrer" className="min-w-0 max-w-full truncate font-semibold text-emerald-800 underline-offset-2 hover:underline dark:text-emerald-300">{s.url.replace(/^https?:\/\/(www\.)?/, '')}</a>
                {s.quote_found === true && <span className="font-semibold text-emerald-700 dark:text-emerald-300">✓ Quote found on the page</span>}
                {s.quote_found === false && <span className="font-semibold text-red-700 dark:text-red-300">✕ Quote not on the page</span>}
                {s.quote_found === null && <span className="text-stone-500">Page couldn&apos;t be read</span>}
              </div>
            </li>
          ))}
        </ol>
      </section>

      {check.coverage.length > 0 && (
        <section className="mt-6">
          <h3 className="text-[11px] font-bold uppercase tracking-[0.14em] text-emerald-800 dark:text-emerald-300">How it was covered</h3>
          <ul className="mt-2 divide-y divide-stone-200 dark:divide-stone-800">
            {check.coverage.map((c, i) => (
              <li key={i} className="flex items-start justify-between gap-3 py-2 text-sm">
                <a href={c.url} target="_blank" rel="noreferrer" className="min-w-0 hover:underline"><b>{c.outlet}</b> · {c.title}</a>
                <span className="shrink-0 rounded-full bg-stone-100 px-2 py-0.5 text-xs font-semibold text-stone-600 dark:bg-stone-800 dark:text-stone-300">{OWNERSHIP[c.outlet_type] ?? c.outlet_type}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-6 grid gap-3 border-t border-stone-200 pt-5 dark:border-stone-800">
        <label htmlFor={`note-${check.id}`} className="text-sm font-semibold">Editor&apos;s note</label>
        <textarea
          id={`note-${check.id}`}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
          placeholder="Why you approved, held or rejected it. Notes feed the next round of tuning."
          className="rounded-xl border border-stone-300 bg-white p-3 text-sm outline-none focus:border-emerald-700 dark:border-stone-700 dark:bg-stone-950"
        />
        <div className="flex flex-wrap gap-2">
          <button disabled={busy} onClick={() => onDecide('approve')} className="h-10 rounded-xl bg-emerald-800 px-4 text-sm font-semibold text-white disabled:opacity-50">Approve</button>
          <button disabled={busy} onClick={() => onDecide('hold')} className="h-10 rounded-xl border border-stone-300 px-4 text-sm font-semibold disabled:opacity-50 dark:border-stone-700">Hold</button>
          <button disabled={busy} onClick={() => onDecide('reject')} className="h-10 rounded-xl border border-red-300 px-4 text-sm font-semibold text-red-800 disabled:opacity-50 dark:border-red-900 dark:text-red-300">Reject</button>
          {check.review_status !== 'pending' && (
            <button disabled={busy} onClick={() => onDecide('reopen')} className="h-10 rounded-xl px-4 text-sm font-semibold text-stone-600 disabled:opacity-50 dark:text-stone-400">Move back to pending</button>
          )}
        </div>
        <p className="text-xs text-stone-500">
          Checked {ago(check.created_at)} · cost ${Number(check.cost_usd ?? 0).toFixed(3)}
          {check.recheck_at ? ` · re-check due ${new Date(check.recheck_at).toLocaleString()}` : ''}
          {check.reviewed_at ? ` · reviewed ${ago(check.reviewed_at)}` : ''}
        </p>
      </section>
    </article>
  )
}
