'use client'

import { useState } from 'react'
import { ArrowUpRight, ChevronRight, Info, X } from 'lucide-react'
import edition from '@/data/focus-topics.json'
import { CanopyModal } from './modal'

/** Reviewed public sources only. Expired editions never masquerade as current news. */
export function InFocus({ onChoose, onDismiss }: { onChoose: (question: string) => void; onDismiss: () => void }) {
  const [details, setDetails] = useState(false)
  const [index, setIndex] = useState(0)
  const day = new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Lusaka', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
  const available = day >= edition.reviewed && day < edition.expires
  const topic = edition.topics[index]
  // Just the question. The Bill is already in the library, so retrieval finds
  // it instantly; prefilling the parliament.gov.zm URL made the agent's first
  // move a fetch from a server that can hang for over a minute, and dumped a
  // 250-character URL into the composer on phones.
  const choose = () => { onChoose(topic.question); setDetails(false) }
  return <>
    <section className="cp-in-focus" aria-label="Suggested question">
      <div className="cp-focus-heading"><span>In focus · Zambia</span><button type="button" aria-label="Hide suggested questions" onClick={onDismiss}><X size={16} /></button></div>
      {available ? <>
        <button type="button" className="cp-focus-question" onClick={choose} aria-label={`Discuss: ${topic.question}`}><span>{topic.question}</span><ArrowUpRight size={17} /></button>
        <div className="cp-focus-meta"><button type="button" aria-label={`Source and status: ${topic.source}`} onClick={() => setDetails(true)}>{topic.kind} · {topic.published}<Info size={13} /></button><button type="button" onClick={() => setIndex(value => (value + 1) % edition.topics.length)}>Another topic<ChevronRight size={13} /></button></div>
      </> : <p>The next source review is pending. Try an example or ask your own question.</p>}
    </section>
    {details && available && <CanopyModal title="Behind this question" onClose={() => setDetails(false)}>
      <h3>{topic.question}</h3><p>{topic.context}</p><p>{topic.status}</p>
      <a className="cp-focus-source" href={topic.url} target="_blank" rel="noopener noreferrer">{topic.sourceTitle}<ArrowUpRight size={18} /></a>
      <p className="cp-focus-meta">Sources reviewed {edition.reviewed}. Review due {edition.expires}.</p>
      <button type="button" className="cp-btn primary" onClick={choose}>Use this question</button>
    </CanopyModal>}
  </>
}
