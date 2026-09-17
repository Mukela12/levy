'use client'

/**
 * Sources and citations under a Canopy answer.
 *
 * Rows come from the typed source model: retrieved passages grouped by
 * document, audit verdicts (verified / not in library / foreign / conflicting
 * number or year / repealed) and web results. Only an actual verified verdict with a
 * document id earns the positive badge, and the badge means "matched in
 * Levy's library", nothing more; the explainer says so in words.
 */

import { useId, useState } from 'react'
import { ArrowRight, ArrowUpRight, BookOpen, ChevronDown, ChevronUp, FileText, Globe, Info, Scale } from 'lucide-react'
import { CanopyModal as Dialog } from './modal'
import type { ChunkUsed, CitationVerdict, WebSource } from '@/lib/api'
import type { MessageBlock } from '@/components/chat/chat-message'
import { passageLabel, sourceModel, type SourceRow } from '@/lib/source-model'

export function CitationSeal({ size = 22 }: { size?: number }) {
  // eslint-disable-next-line @next/next/no-img-element
  return <img className="cp-status-art" src="/canopy/status-verified.png" width={size} height={size} alt="" aria-hidden="true" />
}
function ReviewSeal({ size = 22 }: { size?: number }) {
  // eslint-disable-next-line @next/next/no-img-element
  return <img className="cp-status-art" src="/canopy/status-review.png" width={size} height={size} alt="" aria-hidden="true" />
}

function badgeLabel(row: SourceRow): string {
  if (row.verification === 'verified') return 'Verified'
  if (row.lawStatus === 'repealed') return 'Repealed'
  if (row.foreign) return 'Foreign authority'
  if (row.conflict) return 'Check citation'
  if (row.documentId) return 'Check result'
  return 'Not in library'
}

/** "Repealed · replaced by the Children's Code Act, 2022" */
function lawStatusText(row: SourceRow): string | null {
  const by = row.replacedBy.join(' and ')
  if (row.lawStatus === 'repealed') return by ? `Repealed · replaced by the ${by}` : 'Repealed'
  if (row.lawStatus === 'repeal pending') return by ? `Still in force · the ${by} will replace it once it starts` : 'Still in force · a replacement has been passed'
  return null
}

function Badge({ row, onClick }: { row: SourceRow; onClick: () => void }) {
  if (row.verification === 'none') {
    return <span className="cp-source-origin">{row.type === 'web' ? 'Web source' : 'Retrieved'}</span>
  }
  const verified = row.verification === 'verified'
  return (
    <button type="button" className={'cp-citation-badge' + (verified ? ' is-verified' : ' needs-review')} onClick={onClick} aria-label={`${verified ? 'Verified library match' : 'Review citation'}: ${row.title}`}>
      {verified ? <CitationSeal /> : <ReviewSeal />}
      <span>{badgeLabel(row)}</span>
    </button>
  )
}

export interface AnswerSourcesProps {
  citations?: ChunkUsed[]
  webSources?: WebSource[]
  blocks?: MessageBlock[]
  /** Open the real document viewer at a passage, or at page 1 for an authority-only match. */
  onOpenPassage: (passage: ChunkUsed) => void
  onOpenDocument: (documentId: string, title: string) => void
}

export function AnswerSources({ citations, webSources, blocks, onOpenPassage, onOpenDocument }: AnswerSourcesProps) {
  const model = sourceModel({ citations, webSources, blocks })
  const [expanded, setExpanded] = useState(true)
  const [all, setAll] = useState(false)
  const [detail, setDetail] = useState<SourceRow | null>(null)
  const [explain, setExplain] = useState(false)
  const listId = useId()
  if (!model.rows.length) return null

  const attention = model.rows.filter((r) => r.verification === 'review')
  const rest = model.rows.filter((r) => r.verification !== 'review')
  const visible = [...attention, ...(all ? rest : rest.slice(0, 3))]

  function open(row: SourceRow) {
    if (row.type === 'web') {
      if (row.href) window.open(row.href, '_blank', 'noopener,noreferrer')
      return
    }
    if (row.passages.length) onOpenPassage(row.passages[0])
    else if (row.documentId) onOpenDocument(row.documentId, row.title)
    else setDetail(row)
  }

  return (
    <section className="cp-sources" aria-label="Sources and citations">
      <header className="cp-sources-head">
        <button type="button" className="cp-sources-disclosure" aria-expanded={expanded} aria-controls={listId} onClick={() => setExpanded((v) => !v)}>
          <BookOpen size={17} />
          <strong>Sources &amp; citations</strong>
          <span className="cp-sources-count">{model.rows.length}</span>
          {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </button>
        <button type="button" className="cp-source-help" aria-label="What does verified mean?" onClick={() => setExplain(true)}>
          <Info size={16} />
        </button>
      </header>
      <div className="cp-source-summary" role="status">
        {model.verified > 0 && (
          <span className="cp-source-matched">
            <CitationSeal size={19} />
            {model.verified} library {model.verified === 1 ? 'match' : 'matches'}
          </span>
        )}
        {model.review > 0 && (
          <button type="button" className="cp-source-attention" onClick={() => { setExpanded(true); setDetail(attention[0]) }}>
            <ReviewSeal size={19} />
            {model.review} to review <ArrowRight size={12} />
          </button>
        )}
        {!model.verified && !model.review && (
          <span>{model.state === 'complete' ? 'No citation verdicts returned' : 'No citation check recorded'}</span>
        )}
      </div>
      {expanded && (
        <div id={listId}>
          <ol className="cp-source-list">
            {visible.map((row) => (
              <li className={'cp-source-row' + (row.verification === 'review' ? ' is-review' : '')} key={row.id}>
                <span className="cp-source-icon" aria-hidden="true">
                  {row.type === 'web' ? <Globe size={19} /> : row.kind === 'case' ? <Scale size={19} /> : <FileText size={19} />}
                </span>
                <div className="cp-source-main">
                  <div className="cp-source-topline">
                    <span>{row.type === 'web' ? row.domain || 'External website' : row.kind === 'case' ? 'Judgment' : row.kind === 'statute' ? 'Legislation' : 'Library source'}</span>
                    <Badge row={row} onClick={() => setDetail(row)} />
                  </div>
                  <button type="button" className="cp-source-title" onClick={() => open(row)}>
                    {row.title}
                    <ArrowUpRight size={14} />
                  </button>
                  {row.lawStatus && (
                    <div className={'cp-source-law' + (row.lawStatus === 'repealed' ? ' is-repealed' : ' is-pending')}>{lawStatusText(row)}</div>
                  )}
                  <div className="cp-source-context">
                    {row.passages.length ? (
                      <>
                        <span>{row.passages.length} {row.passages.length === 1 ? 'passage' : 'passages'}</span>
                        <span aria-hidden="true">·</span>
                        <span>{passageLabel(row.passages[0])}</span>
                        {row.passages.length > 1 && (
                          <span className="cp-passage-links">
                            {row.passages.slice(0, 6).map((p, i) => (
                              <button key={p.id || i} type="button" onClick={() => onOpenPassage(p)}>{passageLabel(p)}</button>
                            ))}
                          </span>
                        )}
                      </>
                    ) : (
                      <span>
                        {row.type === 'web'
                          ? 'External reference'
                          : row.conflict
                            ? 'Cited details differ from the matched document'
                            : row.foreign
                              ? 'Outside the Zambian library · check the original report'
                              : row.type === 'unmatched'
                                ? 'Check the original authority before relying on it'
                                : 'Mentioned in the answer · no retrieved passage attached'}
                      </span>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ol>
          {rest.length > 3 && (
            <button type="button" className="cp-sources-more" onClick={() => setAll((v) => !v)}>
              {all ? 'Show fewer sources' : `Show ${rest.length - 3} more ${rest.length - 3 === 1 ? 'source' : 'sources'}`}
              {all ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          )}
        </div>
      )}

      {explain && (
        <Dialog title="What verified means" onClose={() => setExplain(false)}>
          <div className="cp-verify-intro">
            <span className="cp-source-art" aria-hidden="true">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/canopy/verify-analyse.png" width={100} height={100} alt="" decoding="async" />
              <span className="cp-source-art-seal"><CitationSeal size={26} /></span>
            </span>
            <h3>Matched in Levy’s library.</h3>
          </div>
          <p>The badge means the authority named in the answer matched a document in the library.</p>
          <p>It does not confirm the exact quotation or that the passage supports the answer.</p>
          <p>An Act the library records as repealed is marked Repealed instead, with the Act that replaced it.</p>
          <div className="cp-verify-boundary"><Info size={17} /><span>Search relevance scores and web links are separate from citation verification.</span></div>
        </Dialog>
      )}

      {detail && (
        <Dialog title="Citation check" onClose={() => setDetail(null)}>
          <div className="cp-source-detail">
            <div className="cp-source-kicker">{detail.type === 'web' ? 'External source' : detail.kind === 'case' ? 'Judgment' : 'Library reference'}</div>
            <h2>{detail.title}</h2>
            <div className={'cp-citation-verdict' + (detail.verification === 'verified' ? ' is-positive' : '')}>
              {detail.verification === 'verified' ? <CitationSeal size={40} /> : <Info size={19} />}
              <div>
                <h3>
                  {detail.verification === 'verified'
                    ? 'Authority matched in the library'
                    : detail.lawStatus === 'repealed' && !detail.conflict
                      ? 'This Act has been repealed'
                      : detail.foreign
                        ? 'Foreign authority · check the original report'
                        : detail.conflict
                          ? 'Citation details need review'
                          : detail.type === 'web'
                            ? 'A web link is not a verified citation'
                            : detail.verdicts.length
                              ? 'No confirmed library match'
                              : 'No citation verdict recorded'}
                </h3>
                <p>
                  {detail.verification === 'verified'
                    ? detail.lawStatus === 'repeal pending'
                      ? `This Act is still law, but ${detail.replacedBy.length ? `the ${detail.replacedBy.join(' and ')}` : 'a new Act'} will replace it once the Minister sets a start date. Check whether that has happened before relying on the answer.`
                      : 'Check the passage and the document’s current status before relying on the answer.'
                    : detail.lawStatus === 'repealed' && !detail.conflict
                      ? `The answer cites this Act, but ${detail.replacedBy.length ? `the ${detail.replacedBy.join(' and ')} repealed it` : 'a later Act repealed it'}. Unless the question is about what the law used to be, check the answer against the Act that replaced it.`
                      : detail.foreign
                        ? 'This authority was identified as outside the Zambian library. Check its original report and its relevance to the Zambian question.'
                        : detail.conflict
                          ? 'The number or year in the answer differs from the library record. Check which instrument was intended.'
                          : detail.type === 'web'
                            ? 'Review the publisher, publication date and source content directly.'
                            : detail.verdicts.some((c) => c.status === 'not_found')
                              ? 'Levy could not match this authority in its library. It may exist elsewhere; this is not a finding that it is invented.'
                              : 'A missing or incomplete check cannot establish verification.'}
                </p>
              </div>
            </div>
            {detail.verdicts.map((v: CitationVerdict, i) => (
              <dl className="cp-citation-comparison" key={i}>
                <div><dt>Cited in answer</dt><dd>{v.text}</dd></div>
                {v.title && <div><dt>Matched document</dt><dd>{v.title}</dd></div>}
                {v.law_status && (
                  <div><dt>Status</dt><dd>{v.law_status === 'repealed'
                    ? v.replaced_by?.length ? `Repealed by the ${v.replaced_by.join(' and the ')}` : 'Repealed'
                    : v.replaced_by?.length ? `In force until the ${v.replaced_by.join(' and the ')} starts` : 'In force, replacement passed'}</dd></div>
                )}
              </dl>
            ))}
            <div className="cp-verify-boundary"><Info size={17} /><span>Library matching does not check subsequent treatment, exact quotations or whether a passage supports the answer. Repeal flags cover only the Acts the library records as repealed.</span></div>
            {(detail.documentId || detail.passages.length > 0) && (
              <button type="button" className="cp-btn primary" style={{ marginTop: 16 }} onClick={() => { const row = detail; setDetail(null); open(row) }}>
                Open the document <ArrowUpRight size={15} />
              </button>
            )}
          </div>
        </Dialog>
      )}
    </section>
  )
}
