'use client'

/**
 * Canopy Legislation directory. 841 Acts is a phone book, so it reads like
 * one: a search that filters as you type, an A to Z rail that jumps, letter
 * sections, and compact rows that scale from one column on a phone to three
 * on a wide screen. The legacy SEO markup is rendered untouched for the
 * legacy variant (and for crawlers, which see the server HTML).
 */

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { ArrowUpRight, Search, X } from 'lucide-react'
import { useUiVariant } from '@/lib/ui-variant'
import type { ActSummary } from '@/lib/server/corpus'

export function ActsDirectory({ acts, children }: { acts: ActSummary[]; children: React.ReactNode }) {
  const { variant } = useUiVariant()
  const [query, setQuery] = useState('')
  const trimmed = query.trim().toLowerCase()

  const groups = useMemo(() => {
    const visible = trimmed
      ? acts.filter((a) => `${a.name} ${a.year ?? ''} ${a.actNumber ?? ''}`.toLowerCase().includes(trimmed))
      : acts
    const byLetter = new Map<string, ActSummary[]>()
    for (const a of visible) {
      const k = /[a-z]/i.test(a.name[0]) ? a.name[0].toUpperCase() : '#'
      if (!byLetter.has(k)) byLetter.set(k, [])
      byLetter.get(k)!.push(a)
    }
    return { letters: [...byLetter.keys()].sort(), byLetter, count: visible.length }
  }, [acts, trimmed])

  if (variant !== 'canopy') return children

  return (
    <div className="cp-acts-directory">
      <header className="cp-acts-head">
        <div>
          <h1>Legislation</h1>
          <p>Browse the Zambian Acts in Levy&rsquo;s library. Check the original text and current status before relying on a provision.</p>
        </div>
      </header>

      <div className="cp-acts-tools">
        <label className="cp-acts-search">
          <Search size={18} aria-hidden="true" />
          <input aria-label="Find an Act" placeholder="Search by Act, number or year…" value={query} onChange={(e) => setQuery(e.target.value)} />
          {query && (
            <button type="button" aria-label="Clear search" onClick={() => setQuery('')}>
              <X size={16} />
            </button>
          )}
        </label>
        <p role="status">
          {groups.count} {groups.count === 1 ? 'Act' : 'Acts'}
          {trimmed ? ' found' : ' in the library'}
        </p>
      </div>

      {!trimmed && groups.letters.length > 3 && (
        <nav className="cp-acts-alpha" aria-label="Jump to letter">
          {groups.letters.map((l) => (
            <a key={l} href={`#acts-${l}`}>{l}</a>
          ))}
        </nav>
      )}

      {groups.letters.map((l) => (
        <section key={l} id={`acts-${l}`} className="cp-acts-section">
          <h2>{l}</h2>
          <div className="cp-acts-grid">
            {groups.byLetter.get(l)!.map((act) => (
              <Link href={`/acts/${act.slug}`} className="cp-act-row" key={act.id}>
                <span className="cp-act-name">
                  {act.name}
                  {act.status?.status === 'repealed' && <span className="cp-act-flag is-repealed">Repealed</span>}
                  {act.status?.status === 'bill, not yet law' && <span className="cp-act-flag">Bill</span>}
                  {act.status?.status === 'repeal pending' && <span className="cp-act-flag is-pending">Replacement pending</span>}
                </span>
                <span className="cp-act-meta">
                  {[act.actNumber, act.year && !act.actNumber?.includes(String(act.year)) ? act.year : null].filter(Boolean).join(' · ') || 'Library text'}
                </span>
                <ArrowUpRight size={15} aria-hidden="true" />
              </Link>
            ))}
          </div>
        </section>
      ))}

      {!groups.count && (
        <div className="cp-acts-empty">
          <p>No Act matches &ldquo;{query.trim()}&rdquo;.</p>
          <button className="cp-btn" onClick={() => setQuery('')}>Clear search</button>
        </div>
      )}
    </div>
  )
}
