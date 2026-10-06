'use client'

import { useState } from 'react'
import { ArrowUpRight, ChevronRight, Info, X } from 'lucide-react'
import edition from '@/data/focus-topics.json'
import { CanopyModal } from './modal'

const DAY_MS = 86400000

/**
 * Reviewed public sources only. Once an edition's review date passes, its
 * questions stay on offer under "Suggested" with the date the sources were
 * last checked, so an overdue edition never poses as current news and the
 * welcome screen never goes blank (it showed only a "pending" notice for a
 * week in October 2026).
 */
export function InFocus({ onChoose, onDismiss }: { onChoose: (question: string) => void; onDismiss: () => void }) {
  const [details, setDetails] = useState(false)
  const day = new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Lusaka', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
  const current = day >= edition.reviewed && day < edition.expires
  const overdue = day >= edition.expires
  // A different question leads each day, so a monthly edition does not greet
  // a returning visitor with the same question for four weeks.
  const lead = Math.max(0, Math.floor((Date.parse(day) - Date.parse(edition.reviewed)) / DAY_MS)) % edition.topics.length
  const [index, setIndex] = useState(lead)
  const topic = edition.topics[index]
  // Just the question. The Bill is already in the library, so retrieval finds
  // it instantly; prefilling the parliament.gov.zm URL made the agent's first
  // move a fetch from a server that can hang for over a minute, and dumped a
  // 250-character URL into the composer on phones.
  const choose = () => { onChoose(topic.question); setDetails(false) }
  return <>
    <section className="cp-in-focus" aria-label="Suggested question">
      <div className="cp-focus-heading"><span>{current ? 'In focus · Zambia' : 'Suggested · Zambia'}</span><button type="button" aria-label="Hide suggested questions" onClick={onDismiss}><X size={16} /></button></div>
      <button type="button" className="cp-focus-question" onClick={choose} aria-label={`Discuss: ${topic.question}`}><span>{topic.question}</span><ArrowUpRight size={17} /></button>
      <div className="cp-focus-meta"><button type="button" aria-label={`Source and status: ${topic.source}`} onClick={() => setDetails(true)}>{topic.kind} · {topic.published}<Info size={13} /></button><button type="button" onClick={() => setIndex(value => (value + 1) % edition.topics.length)}>Another topic<ChevronRight size={13} /></button></div>
    </section>
    {details && <CanopyModal title="Behind this question" onClose={() => setDetails(false)}>
      <h3>{topic.question}</h3><p>{topic.context}</p><p>{topic.status}</p>
      <a className="cp-focus-source" href={topic.url} target="_blank" rel="noopener noreferrer">{topic.sourceTitle}<ArrowUpRight size={18} /></a>
      <p className="cp-focus-meta">{current
        ? `Sources reviewed ${edition.reviewed}. Review due ${edition.expires}.`
        : `Sources last reviewed ${edition.reviewed}.${overdue ? ' A newer review is overdue, so check the status note before relying on it.' : ''}`}</p>
      <button type="button" className="cp-btn primary" onClick={choose}>Use this question</button>
    </CanopyModal>}
  </>
}
