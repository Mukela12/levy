'use client'

import { useState } from 'react'
import Link from 'next/link'
import { BookOpen, ArrowUpRight, Search } from 'lucide-react'
import { useUiVariant } from '@/lib/ui-variant'
import type { ActSummary } from '@/lib/server/corpus'

export function ActsDirectory({ acts, children }: { acts: ActSummary[]; children: React.ReactNode }) {
  const { variant } = useUiVariant()
  const [query, setQuery] = useState('')
  if (variant !== 'canopy') return children
  const visible = acts.filter(a => `${a.name} ${a.year ?? ''} ${a.actNumber ?? ''}`.toLowerCase().includes(query.trim().toLowerCase()))
  return <div className="cp-acts-directory">
    <h1>Legislation</h1>
    <p>Browse the Zambian Acts in Levy’s library. Check the original text and current status before relying on a provision.</p>
    <label className="cp-acts-search"><Search size={18} aria-hidden="true" /><input aria-label="Find an Act" placeholder="Search by Act, number or year…" value={query} onChange={e => setQuery(e.target.value)} /></label>
    <p role="status">{visible.length} {visible.length === 1 ? 'Act' : 'Acts'}{query.trim() ? ' found' : ' in the library'}</p>
    <div className="cp-acts-grid">{visible.map(act => <Link href={`/acts/${act.slug}`} className="cp-act-card" key={act.id}>
      <BookOpen size={22} aria-hidden="true" />
      <h2>{act.name}</h2>
      <div><span>{[act.actNumber, act.year && !act.actNumber?.includes(String(act.year)) ? act.year : null, 'Library text'].filter(Boolean).join(' · ')}</span><ArrowUpRight size={17} aria-hidden="true" /></div>
    </Link>)}</div>
    {!visible.length && <button className="cp-btn" onClick={() => setQuery('')}>Clear search</button>}
  </div>
}
