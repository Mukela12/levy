/**
 * View model for an answer's sources and citation verdicts.
 *
 * Ported from the design lab's citationModel.js onto the real API types.
 * Rules that matter:
 *  - Retrieval similarity is never verification evidence. A retrieved passage
 *    is shown as "retrieved"; only a citation-audit verdict can mark a row
 *    verified.
 *  - A positive badge needs a verified verdict WITH a document id, no foreign
 *    flag and no number/year conflict between what the answer cited and what
 *    the library matched. A conflict is shown as "check citation".
 *  - Missing audit data is neutral ("no citation check recorded"), never a
 *    pending spinner and never a positive badge.
 */
import type { ChunkUsed, CitationVerdict, WebSource } from '@/lib/api'
import type { MessageBlock } from '@/components/chat/chat-message'

export type SourceVerification = 'verified' | 'review' | 'none'

export interface SourceRow {
  id: string
  type: 'library' | 'unmatched' | 'web'
  documentId?: string
  title: string
  kind?: 'case' | 'statute'
  passages: ChunkUsed[]
  verdicts: CitationVerdict[]
  href?: string | null
  domain?: string
  preview?: string
  conflict: boolean
  foreign: boolean
  verification: SourceVerification
}

export interface SourceModel {
  rows: SourceRow[]
  state: 'complete' | 'unavailable'
  verified: number
  review: number
}

export function safeSourceUrl(value?: string | null): string | null {
  if (!value) return null
  try {
    const u = new URL(value)
    return ['https:', 'http:'].includes(u.protocol) ? u.href : null
  } catch {
    return null
  }
}

const yearOf = (s?: string) => String(s || '').match(/\b(?:19|20)\d{2}\b/)?.[0]
const numberOf = (s?: string) => String(s || '').match(/\bNo\.?\s*(\d+)/i)?.[1]

/** The answer cited a number or year that differs from the matched instrument. */
export function citationConflict(c: CitationVerdict): boolean {
  if (c.kind !== 'statute' || !c.title) return false
  const yt = yearOf(c.text)
  const yd = yearOf(c.title)
  const nt = numberOf(c.text)
  const nd = numberOf(c.title)
  return Boolean((yt && yd && yt !== yd) || (nt && nd && nt !== nd))
}

export function sourceModel({
  citations = [],
  webSources = [],
  blocks = [],
}: {
  citations?: ChunkUsed[]
  webSources?: WebSource[]
  blocks?: MessageBlock[]
}): SourceModel {
  const audits = blocks.filter((b): b is Extract<MessageBlock, { kind: 'citation_audit' }> => b.kind === 'citation_audit')
  const state: SourceModel['state'] = audits.length ? 'complete' : 'unavailable'
  const verdicts = audits.length ? audits[audits.length - 1].citations || [] : []

  const rows: SourceRow[] = []
  const docs = new Map<string, SourceRow>()
  citations.forEach((c, i) => {
    const key = c.document_id ? `doc:${c.document_id}` : `legacy:${c.id || i}`
    let row = docs.get(key)
    if (!row) {
      row = {
        id: key,
        type: 'library',
        documentId: c.document_id,
        title: c.act_name || 'Untitled source',
        passages: [],
        verdicts: [],
        conflict: false,
        foreign: false,
        verification: 'none',
      }
      docs.set(key, row)
      rows.push(row)
    }
    if (!row.passages.some((p) => p.id && p.id === c.id)) row.passages.push(c)
  })

  const seen = new Set<string>()
  verdicts.forEach((c, i) => {
    const identity = [c.kind, c.text, c.document_id, c.status].join('|')
    if (seen.has(identity)) return
    seen.add(identity)
    let row = c.document_id ? docs.get(`doc:${c.document_id}`) : undefined
    if (!row) {
      row = {
        id: c.document_id ? `doc:${c.document_id}` : `audit:${i}`,
        type: c.document_id ? 'library' : 'unmatched',
        documentId: c.document_id,
        title: c.title || c.text || 'Citation',
        kind: c.kind,
        passages: [],
        verdicts: [],
        conflict: false,
        foreign: false,
        verification: 'none',
      }
      rows.push(row)
      if (c.document_id) docs.set(row.id, row)
    }
    row.kind = c.kind
    row.verdicts.push(c)
  })

  for (const row of rows) {
    row.conflict = row.verdicts.some(citationConflict)
    row.foreign = row.verdicts.some((c) => c.foreign === true)
    row.verification =
      state !== 'complete'
        ? 'none'
        : row.verdicts.some((c) => c.status !== 'verified' || !c.document_id) || row.conflict || row.foreign
          ? 'review'
          : row.verdicts.length
            ? 'verified'
            : 'none'
  }

  const urls = new Set<string>()
  webSources.forEach((w, i) => {
    const href = safeSourceUrl(w.url)
    const key = href || w.url || `web:${i}`
    if (urls.has(key)) return
    urls.add(key)
    rows.push({
      id: `web:${key}`,
      type: 'web',
      title: w.title || w.domain || 'Web source',
      href,
      domain: href ? new URL(href).hostname : w.domain,
      preview: w.snippet,
      passages: [],
      verdicts: [],
      conflict: false,
      foreign: false,
      verification: 'none',
    })
  })

  return {
    rows,
    state,
    verified: rows.filter((r) => r.verification === 'verified').length,
    review: rows.filter((r) => r.verification === 'review').length,
  }
}

export function passageLabel(p: ChunkUsed): string {
  const bits: string[] = []
  if (p.section) bits.push(`Section ${p.section}`)
  if (p.part) bits.push(`Part ${p.part}`)
  if (p.page_start) bits.push(`p. ${p.page_start}${p.page_end && p.page_end !== p.page_start ? `–${p.page_end}` : ''}`)
  return bits.join(' · ') || 'Retrieved passage'
}
