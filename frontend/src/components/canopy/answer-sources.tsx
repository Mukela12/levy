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
import { ArrowRight, ArrowUpRight, BookOpen, ChevronDown, ChevronUp, FileText, Globe, History, Info, Scale } from 'lucide-react'
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

/** Cited sections the answer relies on without saying they are dead. */
function unnamedDead(row: SourceRow) {
  return row.deadSections.filter((d) => !d.acknowledged)
}

/** "Section 24 repealed" / "Sections 24 and 31 no longer law" */
function deadLabel(row: SourceRow): string {
  const dead = unnamedDead(row)
  if (dead.length === 1) return `Section ${dead[0].section} ${dead[0].status}`
  return 'Sections no longer law'
}

/** "Section 24 repealed · by the Immigration and Deportation (Amendment) Act, 2016 (No. 19 of 2016)" */
function deadSectionText(d: SourceRow['deadSections'][number]): string {
  return d.status === 'repealed'
    ? `Section ${d.section} repealed · by the ${d.by}`
    : `Section ${d.section} replaced · the current wording is in the ${d.by}`
}

const TREATMENT_LABEL: Record<string, string> = { reversed: 'Reversed', 'departed from': 'Departed from', 'held per incuriam': 'Per incuriam' }

function badgeLabel(row: SourceRow): string {
  if (row.verification === 'verified') return 'Verified'
  if (row.verification === 'known') return `Cited in ${row.known?.cited_by ?? 0} judgments`
  if (row.quoteIssues.length) return 'Check quotation'
  if (row.treatment.length && !row.treatmentNamed) return TREATMENT_LABEL[row.treatment[0].treatment] || 'Later treatment'
  if (row.known?.year_conflict) return 'Check citation'
  if (row.lawStatus === 'repealed') return 'Repealed'
  if (row.lawStatus === 'not in force') return 'Not in force yet'
  if (unnamedDead(row).length) return deadLabel(row)
  if (row.foreign) return 'Foreign authority'
  if (row.conflict) return 'Check citation'
  if (row.documentId) return 'Check result'
  return 'Not in library'
}

/** ["Road Traffic Act, 2002", "Public Roads Act, 2002"] -> "the Road Traffic Act, 2002 and the Public Roads Act, 2002" */
function theActs(names: string[]): string {
  return names.map((n) => `the ${n}`).join(' and ')
}

/** "Repealed · replaced by the Children's Code Act, 2022" */
function lawStatusText(row: SourceRow): string | null {
  const by = theActs(row.replacedBy)
  if (row.lawStatus === 'repealed') return by ? `Repealed · replaced by ${by}` : 'Repealed'
  if (row.lawStatus === 'repeal pending') return by ? `Commencement unverified · replacement: ${by}` : 'Commencement unverified · a replacement has been passed'
  if (row.lawStatus === 'not in force') {
    const still = theActs(row.stillApplies)
    return still ? `Not shown to be in force · ${still} still applies` : 'Passed · no commencement order recorded'
  }
  return null
}

/** The Act's status as read off retrieved passages the answer did not cite. */
function passageLawText(row: SourceRow): string | null {
  if (row.passageLaw === 'repealed') return 'Retrieved from a repealed Act'
  if (row.passageLaw === 'not in force') return 'Retrieved from an Act passed but not shown to be in force'
  if (row.passageLaw === 'repeal pending') return 'Commencement unverified · a replacement has been passed'
  return null
}

const SECTION_STATE_TEXT = { repealed: 'repealed', replaced: 'repealed and replaced', amended: 'amended since this wording' } as const

const COURT_NAME: Record<string, string> = { SCZ: 'Supreme Court', CCZ: 'Constitutional Court', CAZ: 'Court of Appeal', HC: 'High Court' }

/** "the Court of Appeal in Kingfred Phiri v Life Master Ltd (2024)" */
function treatmentBy(t: SourceRow['treatment'][number]): string {
  const court = COURT_NAME[t.court || ''] ? `the ${COURT_NAME[t.court || '']}` : 'a later court'
  const name = (t.judgment || '').replace(/\s*\((?:APP|Appeal)[^)]*\)\s*$/, '')
  return `${court}${name ? ` in ${name}` : ''}${t.year ? ` (${t.year})` : ''}`
}

/** "Court of Appeal, Kingfred Phiri v Life Master Ltd (2024)" */
function treatmentSource(t: SourceRow['treatment'][number]): string {
  const name = (t.judgment || '').replace(/\s*\((?:APP|Appeal)[^)]*\)\s*$/, '')
  return [COURT_NAME[t.court || ''], name].filter(Boolean).join(', ') + (t.year ? ` (${t.year})` : '')
}

function quoteLine(q: SourceRow['quoteIssues'][number]): string {
  return q.status === 'elsewhere'
    ? `Quoted words are in section ${q.found_in}, not section ${q.section}`
    : `Quoted words not found in section ${q.section ?? ''}`.trim()
}

function verdictHeading(row: SourceRow): string {
  if (row.quoteIssues.length) return row.quoteIssues.every((q) => q.status === 'elsewhere') ? 'The quotation is from another section' : 'The quoted words are not in the cited text'
  if (row.treatment.length && !row.treatmentNamed) return `This case was later ${row.treatment[0].treatment}`
  if (row.verification === 'verified') return row.treatment.length ? 'Authority matched · later treatment named in the answer' : 'Authority matched in the library'
  if (row.verification === 'known') return `Not in the library · cited by ${row.known?.cited_by} judgments it holds`
  if (row.known?.year_conflict) return 'The citation year differs from how courts cite this case'
  if (row.verification === 'noted') return row.lawStatus === 'not in force' ? 'Named in the answer as not yet in force' : 'Named in the answer as repealed'
  if (row.lawStatus === 'repealed' && !row.conflict) return 'This Act has been repealed'
  if (row.lawStatus === 'not in force' && !row.conflict) return 'This Act is not shown to be in force'
  if (unnamedDead(row).length && !row.conflict) {
    return unnamedDead(row).length === 1 ? 'A cited section is no longer law' : 'Cited sections are no longer law'
  }
  if (row.foreign) return 'Foreign authority · check the original report'
  if (row.conflict) return 'Citation details need review'
  if (row.type === 'web') return 'A web link is not a verified citation'
  return row.verdicts.length ? 'No confirmed library match' : 'No citation verdict recorded'
}

function verdictText(row: SourceRow): string {
  const by = theActs(row.replacedBy)
  if (row.quoteIssues.length) {
    const q = row.quoteIssues[0]
    return q.status === 'elsewhere'
      ? `The answer quotes section ${q.section} as saying “${q.quote}”. Those words are in section ${q.found_in}. Check which section the point rests on.`
      : `The answer quotes ${q.section ? `section ${q.section}` : 'this authority'} as saying “${q.quote}”. The library’s text${q.section ? ' of that section' : ''} does not contain those words. Read the source before relying on the quotation.`
  }
  if (row.treatment.length) {
    const t = row.treatment[0]
    const said = row.treatmentNamed ? ' The answer says so.' : ' Check the answer against the later decision before relying on it.'
    const by = treatmentBy(t)
    return `${by.charAt(0).toUpperCase()}${by.slice(1)} ${t.treatment} this case${t.extent ? `: ${t.extent.replace(/^In so far as/, 'in so far as')}` : '.'}${said}`
  }
  if (row.verification === 'known') {
    return `Levy does not hold this judgment, but ${row.known?.cited_by} judgments in its library cite it${row.known?.citation ? ` as ${row.known.citation}` : ''}. That confirms the case exists and how it is cited, not that it supports the answer.`
  }
  if (row.known?.year_conflict) {
    return `Judgments in Levy’s library cite this case${row.known.citation ? ` as ${row.known.citation}` : ''}, with a different year from the answer. Check the report before relying on the citation.`
  }
  if (row.verification === 'verified') {
    return row.lawStatus === 'repeal pending'
      ? `The library records a replacement by ${by || 'a new Act'}, but has not verified its commencement. A missing commencement order is not proof that this Act remains in force. Check the official instrument and relevant date before relying on either Act.`
      : 'Check the passage and the document’s current status before relying on the answer.'
  }
  if (row.verification === 'noted') {
    return row.lawStatus === 'not in force'
      ? 'The answer already says this Act is not yet in force, and the library agrees: it records no commencement order.'
      : `The answer already says this Act is no longer law, and the library agrees: ${by || 'a later Act'} replaced it.`
  }
  if (row.lawStatus === 'not in force' && !row.conflict) {
    const still = theActs(row.stillApplies)
    return `The answer cites this Act as law, but it starts on a date set by statutory instrument and the library records no commencement order. ${still ? `Until it starts, ${still} still applies. ` : ''}Check the Gazette before relying on it.`
  }
  if (row.lawStatus === 'repealed' && !row.conflict) {
    return `The answer cites this Act, but ${by || 'a later Act'} repealed it. Unless the question is about what the law used to be, check the answer against the Act that replaced it.`
  }
  const dead = unnamedDead(row)
  if (dead.length && !row.conflict) {
    const d = dead[0]
    const which = dead.length === 1 ? `section ${d.section}` : `sections ${dead.map((x) => x.section).join(', ')}`
    return d.status === 'repealed' && dead.every((x) => x.status === 'repealed')
      ? `The answer relies on ${which}, which the ${d.by} repealed. Check the answer against the law in force before relying on it.`
      : `${which} has been repealed or replaced since the wording the answer uses (${d.by}). Check the current text before relying on it.`
  }
  if (row.foreign) return 'This authority was identified as outside the Zambian library. Check its original report and its relevance to the Zambian question.'
  if (row.conflict) return 'The number or year in the answer differs from the library record. Check which instrument was intended.'
  if (row.type === 'web') return 'Review the publisher, publication date and source content directly.'
  return row.verdicts.some((c) => c.status === 'not_found')
    ? 'Levy could not match this authority in its library. It may exist elsewhere; this is not a finding that it is invented.'
    : 'A missing or incomplete check cannot establish verification.'
}

function Badge({ row, onClick }: { row: SourceRow; onClick: () => void }) {
  if (row.verification === 'none') {
    return <span className="cp-source-origin">{row.type === 'web' ? 'Web source' : 'Retrieved'}</span>
  }
  if (row.verification === 'noted') {
    // The answer already calls this Act repealed; the badge only confirms it.
    return (
      <button type="button" className="cp-citation-badge is-noted" onClick={onClick} aria-label={`${row.lawStatus === 'not in force' ? 'Act not yet in force' : 'Repealed Act'}, named as such in the answer: ${row.title}`}>
        <History size={14} aria-hidden="true" />
        <span>{row.lawStatus === 'not in force' ? 'Not in force yet' : 'Repealed'}</span>
      </button>
    )
  }
  const verified = row.verification === 'verified'
  if (row.verification === 'known') {
    return (
      <button type="button" className="cp-citation-badge is-known" onClick={onClick} aria-label={`Not in the library, cited by ${row.known?.cited_by} judgments it holds: ${row.title}`}>
        <Scale size={14} aria-hidden="true" />
        <span>{badgeLabel(row)}</span>
      </button>
    )
  }
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
        {model.known > 0 && (
          <span className="cp-source-known">
            <Scale size={16} aria-hidden="true" />
            {model.known} cited in held judgments
          </span>
        )}
        {model.review > 0 && (
          <button type="button" className="cp-source-attention" onClick={() => { setExpanded(true); setDetail(attention[0]) }}>
            <ReviewSeal size={19} />
            {model.review} to review <ArrowRight size={12} />
          </button>
        )}
        {!model.verified && !model.known && !model.review && !model.noted && (
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
                    <div className={'cp-source-law' + (row.verification === 'noted' ? ' is-noted' : row.lawStatus === 'repealed' ? ' is-repealed' : ' is-pending')}>{lawStatusText(row)}</div>
                  )}
                  {!row.lawStatus && row.passageLaw && (
                    <div className={'cp-source-law' + (row.passageLaw === 'repealed' ? ' is-repealed' : ' is-pending')}>{passageLawText(row)}</div>
                  )}
                  {row.quoteIssues.map((q, i) => (
                    <div key={`q-${i}`} className="cp-source-law is-repealed">{quoteLine(q)}</div>
                  ))}
                  {row.treatment.map((t, i) => (
                    <div key={`t-${i}`} className={'cp-source-law' + (row.treatmentNamed ? ' is-noted' : ' is-repealed')}>
                      {TREATMENT_LABEL[t.treatment] || 'Later treatment'} · {treatmentSource(t)}
                    </div>
                  ))}
                  {row.known && (
                    <div className={'cp-source-law' + (row.known.year_conflict ? ' is-pending' : ' is-noted')}>
                      {row.known.year_conflict
                        ? `Judgments Levy holds cite it as ${row.known.citation || 'a different year'}`
                        : `Cited in ${row.known.cited_by} judgments Levy holds${row.known.citation ? ` as ${row.known.citation}` : ''}`}
                    </div>
                  )}
                  {row.deadSections.map((d) => (
                    <div key={d.section} className={'cp-source-law' + (d.acknowledged ? ' is-noted' : ' is-repealed')}>{deadSectionText(d)}</div>
                  ))}
                  {row.passageSections.map((d) => (
                    <div key={`p-${d.section}`} className={'cp-source-law' + (d.state === 'amended' ? ' is-pending' : ' is-repealed')}>
                      Retrieved section {d.section} · {SECTION_STATE_TEXT[d.state]}
                    </div>
                  ))}
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
          <p>Words the answer quotes from a section or a judgment are compared with the library’s text, and flagged when they are not there. A match still does not prove the passage supports the answer.</p>
          <p>A case Levy does not hold, but which judgments in its library cite, shows how many cite it and the citation they use. A case a later court reversed or departed from is marked, once that was confirmed in the later judgment.</p>
          <p>An Act the library records as repealed is marked Repealed instead, with the Act that replaced it. An Act passed but not shown to have started is marked Not in force yet.</p>
          <p>The same labels appear next to citations in the answer: Repealed, Replaced, Amended, or Not in force yet.</p>
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
                <h3>{verdictHeading(detail)}</h3>
                <p>{verdictText(detail)}</p>
              </div>
            </div>
            {detail.verdicts.map((v: CitationVerdict, i) => (
              <dl className="cp-citation-comparison" key={i}>
                <div><dt>Cited in answer</dt><dd>{v.text}</dd></div>
                {v.title && <div><dt>Matched document</dt><dd>{v.title}</dd></div>}
                {v.law_status && (
                  <div><dt>Status</dt><dd>{v.law_status === 'repealed'
                    ? v.replaced_by?.length ? `Repealed by ${theActs(v.replaced_by)}` : 'Repealed'
                    : v.law_status === 'not in force'
                      ? v.still_applies?.length ? `Not shown to be in force; ${theActs(v.still_applies)} still applies` : 'Not shown to be in force'
                      : v.replaced_by?.length ? `Commencement unverified: ${theActs(v.replaced_by)}` : 'Commencement unverified'}</dd></div>
                )}
                {v.section_status?.map((d) => (
                  <div key={d.section}><dt>Section {d.section}</dt><dd>{d.status === 'repealed' ? `Repealed by the ${d.by}` : `Replaced by the ${d.by}`}</dd></div>
                ))}
              </dl>
            ))}
            <div className="cp-verify-boundary"><Info size={17} /><span>Quotations are compared with the library’s text, and later reversals are flagged only once confirmed in the later judgment. Neither check proves a passage supports the answer, and repeal flags cover only the Acts and sections the library records as repealed.</span></div>
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
