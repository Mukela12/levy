'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/components/auth/auth-provider'
import { listMatters, createMatter, type Matter, type MatterDate } from '@/lib/matters'
import { timeAgo } from '@/components/chat/use-recent-sessions'
import { Plus, Loader2, ChevronRight, CalendarDays } from 'lucide-react'

const FILLER = /^(v|vs|and|the|of|in|re|ex|parte|ltd|limited|plc|&)$/i

const words = (s: string) => s.replace(/[^\p{L}\p{N}\s]/gu, ' ').split(/\s+/).filter((w) => w && !FILLER.test(w))

/** Two letters that tell one case from the next, where a list of identical
 *  pictures told the reader nothing. A case name gets one initial per party
 *  ("Mwansa v Zambia Revenue Authority" -> "MZ"); anything else gets its first
 *  and last words ("Estate of the late Joseph Phiri" -> "EP"). */
function monogram(title: string): string {
  const sides = title.split(/\s+(?:v|vs)\.?\s+/i)
  if (sides.length > 1) {
    const [a, b] = [words(sides[0]), words(sides[1])]
    if (a.length && b.length) return (a[0][0] + b[0][0]).toUpperCase()
  }
  const w = words(title)
  if (!w.length) return '·'
  return (w[0][0] + (w.length > 1 ? w[w.length - 1][0] : '')).toUpperCase()
}

/** The soonest key date still ahead, which is what a lawyer scans a case list for. */
function nextKeyDate(m: Matter): MatterDate | null {
  const today = new Date().toISOString().slice(0, 10)
  return (m.key_dates || [])
    .filter((d) => /^\d{4}-\d{2}-\d{2}/.test(d.date || '') && d.date >= today)
    .sort((a, b) => a.date.localeCompare(b.date))[0] ?? null
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// Spelled out by hand: en-GB gives "22 Sept" beside "2 Oct".
function shortDate(iso: string): string {
  return `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]}`
}

export default function MattersPage() {
  const { user, loading: authLoading } = useAuth()
  const router = useRouter()
  const [matters, setMatters] = useState<Matter[]>([])
  const [loading, setLoading] = useState(true)
  // Guests are never "loading": their state is decided by auth alone.
  const busy = user ? loading : authLoading
  const [query, setQuery] = useState('')
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({ title: '', matter_type: '', court: '', cause_number: '' })
  const visibleMatters = matters.filter(m => [m.title, m.matter_type, m.court, m.cause_number].filter(Boolean).join(' ').toLowerCase().includes(query.trim().toLowerCase()))

  useEffect(() => {
    if (!user?.id) return
    listMatters(user.id).then((m) => {
      setMatters(m)
      setLoading(false)
    })
  }, [user?.id])

  async function handleCreate() {
    if (!user?.id || !form.title.trim() || saving) return
    setSaving(true)
    const m = await createMatter(user.id, form)
    setSaving(false)
    if (m) router.push(`/matters/${m.id}`)
  }

  return (
    <div className="min-h-screen text-white/90">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
          <div className="cp-matters-head">
            <h1>Matters</h1>
            <p>Your cases. Levy remembers each one across chats.</p>
          </div>
          {user && <button
            type="button"
            onClick={() => setCreating((v) => !v)}
            className="flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg bg-emerald-500/90 hover:bg-emerald-500 text-black text-[13px] font-medium px-3 py-2 transition-colors"
          >
            <Plus className="size-4" /> New matter
          </button>}
        </div>

        {creating && (
          <div className="mb-6 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.04] p-4">
            <div className="grid sm:grid-cols-2 gap-3">
              <input
                autoFocus
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="Matter title (e.g. Munachonga v Acme Ltd)"
                className="sm:col-span-2 bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-[14px] placeholder:text-white/30 focus:outline-none focus:border-emerald-500/50"
              />
              <input
                value={form.matter_type}
                onChange={(e) => setForm({ ...form, matter_type: e.target.value })}
                placeholder="Type (e.g. Unfair dismissal)"
                className="bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-[14px] placeholder:text-white/30 focus:outline-none focus:border-emerald-500/50"
              />
              <input
                value={form.court}
                onChange={(e) => setForm({ ...form, court: e.target.value })}
                placeholder="Court / division"
                className="bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-[14px] placeholder:text-white/30 focus:outline-none focus:border-emerald-500/50"
              />
              <input
                value={form.cause_number}
                onChange={(e) => setForm({ ...form, cause_number: e.target.value })}
                placeholder="Cause number (if known)"
                className="sm:col-span-2 bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-[14px] placeholder:text-white/30 focus:outline-none focus:border-emerald-500/50"
              />
            </div>
            <div className="flex justify-end gap-2 mt-3">
              <button
                type="button"
                onClick={() => setCreating(false)}
                className="text-[13px] text-white/50 hover:text-white/80 px-3 py-2"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCreate}
                disabled={!form.title.trim() || saving}
                className="flex items-center gap-1.5 rounded-lg bg-emerald-500/90 hover:bg-emerald-500 text-black text-[13px] font-medium px-3 py-2 disabled:opacity-40 transition-colors"
              >
                {saving ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />} Create matter
              </button>
            </div>
          </div>
        )}

        {!busy && matters.length > 0 && <div className="cp-matter-toolbar">
          <p>{matters.length} {matters.length === 1 ? 'matter' : 'matters'} in your workspace</p>
          <input aria-label="Find a matter" placeholder="Find a matter…" value={query} onChange={e => setQuery(e.target.value)} />
        </div>}

        {busy ? (
          <div className="flex items-center gap-2 text-white/40 text-[14px] py-12 justify-center">
            <Loader2 className="size-4 animate-spin" /> Loading your matters…
          </div>
        ) : !user ? (
          <MattersEmpty
            title="Matters live in your account"
            body="Sign in to keep each case's conversations, documents, parties and dates together."
          >
            <Link href="/auth/login" className="cp-signin">Sign in</Link>
          </MattersEmpty>
        ) : matters.length === 0 ? (
          <MattersEmpty
            title="No matters yet"
            body="Open one for a case you are running. Chat inside it and Levy keeps the parties, facts and dates in mind."
          >
            {!creating && (
              <button type="button" className="cp-matters-cta" onClick={() => setCreating(true)}>
                <Plus className="size-4" aria-hidden="true" /> Open your first matter
              </button>
            )}
          </MattersEmpty>
        ) : (
          <div className="cp-matter-list">
            {visibleMatters.length === 0 && <p role="status" className="cp-matter-nomatch">No matters match that search.</p>}
            {visibleMatters.map((m) => {
              const next = nextKeyDate(m)
              const meta = [m.matter_type, m.court, m.cause_number].filter(Boolean).join(' · ')
              return (
                <Link key={m.id} href={`/matters/${m.id}`} className="cp-matter-row group">
                  <span className="cp-matter-mark" aria-hidden="true">{monogram(m.title)}</span>
                  <span className="cp-matter-body">
                    <span className="cp-matter-title">{m.title}</span>
                    <span className="cp-matter-meta">{meta || 'Add the type, court and cause number'}</span>
                  </span>
                  {next ? (
                    <span className="cp-matter-when is-date" title={next.note || undefined}>
                      <CalendarDays className="size-3.5" aria-hidden="true" />
                      {next.label ? `${next.label} · ` : ''}{shortDate(next.date)}
                    </span>
                  ) : m.updated_at ? (
                    <span className="cp-matter-when">Updated {timeAgo(m.updated_at)}</span>
                  ) : null}
                  <ChevronRight className="cp-matter-chev size-4" aria-hidden="true" />
                </Link>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

/** A drawn stack of case files: flat line art in the page's own colours, so
 *  the empty page still says "cases" without a stock render. */
function MattersEmpty({ title, body, children }: { title: string; body: string; children?: React.ReactNode }) {
  return (
    <div className="cp-matters-empty">
      <svg viewBox="0 0 96 72" width="96" height="72" aria-hidden="true">
        <rect x="18" y="8" width="60" height="44" rx="6" className="cp-me-back" />
        <rect x="12" y="16" width="60" height="44" rx="6" className="cp-me-mid" />
        <path d="M6 30a6 6 0 0 1 6-6h18l6 6h42a6 6 0 0 1 6 6v24a6 6 0 0 1-6 6H12a6 6 0 0 1-6-6z" className="cp-me-front" />
        <path d="M20 46h30M20 53h18" className="cp-me-lines" />
      </svg>
      <h2>{title}</h2>
      <p>{body}</p>
      {children}
    </div>
  )
}
