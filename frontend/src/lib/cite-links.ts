/**
 * Turn the citations Levy writes in its prose into links to the document.
 *
 * An answer cites like a lawyer: "[Employment Code Act, Section 53]",
 * "[Children's Code, Section 79(4)]", "[APP No. 36 of 2020, p. 16]", and once
 * an Act is named, "[s. 132(2)]" on its own. Until now the reader had to
 * scroll to the sources panel and find the document by eye.
 *
 * Rules that matter:
 *  - Only a citation that resolves to a document THIS answer used becomes a
 *    link. Everything else stays plain text, so a draft's "[FIRM NAME]" or a
 *    bare "[2007]" is never dressed up as a source.
 *  - A bare section ("[s. 132(2)]") binds to the Act most recently named
 *    before it, in the prose or in an earlier citation. With no Act named,
 *    it stays plain text rather than guessing.
 *  - Code and existing links are left alone.
 */
import type { ChunkUsed, CitationVerdict } from '@/lib/api'
import type { MessageBlock } from '@/components/chat/chat-message'

export interface CiteSource {
  documentId: string
  title: string
  /** Normalised names this document answers to, longest first. */
  keys: string[]
  /** Section number (as written in the text) to the passage that carries it. */
  sections: Map<string, ChunkUsed>
  passage?: ChunkUsed
}

const STOP = new Set(['the', 'of', 'and', 'act', 'code', 'rules', 'regulations', 'zambia', 'republic'])
const norm = (s: string) => (s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()

/** "53(1)" and "Section 53" and "53" all point at section 53. */
function sectionKey(raw: string): string | undefined {
  const m = /(\d+[a-z]?)/i.exec(raw || '')
  return m ? m[1].toLowerCase() : undefined
}

/** "REPUBLIC OF ZAMBIA THE COMPANIES ACT, 2017 (No. 10 of 2017)" -> names to match on. */
function nameKeys(raw: string): string[] {
  const cleaned = (raw || '').replace(/\[[^\]]*\]|\((?:no|cap)[^)]*\)/gi, ' ')
  const base = norm(cleaned).replace(/^republic of zambia /, '').replace(/^the /, '')
  const withoutYear = base.replace(/\b(?:19|20)\d{2}\b/g, '').replace(/\s+/g, ' ').trim()
  const words = withoutYear.split(' ').filter(Boolean)
  const significant = words.filter((w) => !STOP.has(w))
  const keys = [base, withoutYear]
  // "EIZ Act" for the Engineering Institution of Zambia Act, "MRCA" for the
  // Minerals Regulation Commission Act: the model shortens after first use.
  if (significant.length >= 2) keys.push(significant.map((w) => w[0]).join(''))
  return [...new Set(keys.filter((k) => k.length >= 3))].sort((a, b) => b.length - a.length)
}

export function buildCiteIndex(input: {
  citations?: ChunkUsed[] | null
  blocks?: MessageBlock[] | null
}): CiteSource[] {
  const byId = new Map<string, CiteSource>()
  const add = (documentId: string | undefined, title: string, passage?: ChunkUsed) => {
    if (!documentId || !title) return
    let source = byId.get(documentId)
    if (!source) {
      source = { documentId, title, keys: [], sections: new Map() }
      byId.set(documentId, source)
    }
    source.keys = [...new Set([...source.keys, ...nameKeys(title)])].sort((a, b) => b.length - a.length)
    if (passage) {
      source.passage = source.passage ?? passage
      const key = sectionKey(passage.section || '')
      if (key && !source.sections.has(key)) source.sections.set(key, passage)
    }
  }
  for (const c of input.citations || []) add(c.document_id, c.act_name || '', c)
  for (const b of input.blocks || []) {
    if (b.kind !== 'citation_audit') continue
    for (const v of (b.citations || []) as CitationVerdict[]) {
      if (v.status !== 'verified' || !v.document_id) continue
      add(v.document_id, v.title || v.text || '')
      // The answer's own wording ("Children's Code Act No. 12 of 2022") is
      // what the reader sees, so match on that too.
      const source = byId.get(v.document_id)
      if (source && v.text) source.keys = [...new Set([...source.keys, ...nameKeys(v.text)])].sort((a, b) => b.length - a.length)
    }
  }
  return [...byId.values()]
}

function matchByName(name: string, sources: CiteSource[]): CiteSource | undefined {
  const n = norm(name).replace(/^the /, '')
  if (!n || n.length < 3) return undefined
  let best: { source: CiteSource; score: number } | undefined
  for (const source of sources) {
    for (const key of source.keys) {
      const hit = key === n ? key.length + 2 : n.includes(key) || key.includes(n) ? Math.min(key.length, n.length) : 0
      if (hit > (best?.score ?? 0)) best = { source, score: hit }
    }
  }
  return best && best.score >= 4 ? best.source : undefined
}

const SECTION_IN = /\b(?:sections?|ss?\.|art(?:icle)?s?\.?|orders?|rules?|regulations?|reg\.)\s*(\d+[a-z]?)/i
const PAGE_IN = /\b(?:pp?\.|pages?)\s*(\d{1,4})/i
/** Draft placeholders and bare years are not citations. */
const NOT_A_CITE = /^(?:\d{4}|[A-Z][A-Z \-/]{2,}|x{1,3})$/

export interface CiteLink { documentId: string; title: string; page?: number; section?: string }

/** What a bracket's contents point at, given the sources and the Act in hand. */
export function resolveCite(
  inner: string,
  sources: CiteSource[],
  current?: CiteSource,
): { link: CiteLink; source: CiteSource } | undefined {
  const raw = inner.trim()
  if (!raw || NOT_A_CITE.test(raw)) return undefined
  const sectionAt = SECTION_IN.exec(raw)
  const pageAt = PAGE_IN.exec(raw)
  const section = sectionAt?.[1]
  const page = pageAt?.[1]
  // The name is whatever stands before the section or page reference.
  const cut = Math.min(sectionAt?.index ?? raw.length, pageAt?.index ?? raw.length)
  const namePart = raw.slice(0, cut).replace(/[,;:\s]+$/, '')
  const named = matchByName(namePart, sources)
  const hasName = /[a-z]{3}/i.test(namePart)
  // A named citation that matches nothing must not borrow the Act in hand:
  // "[Subordinate Courts Act, Section 38]" is not the Act we just quoted.
  const chosen = named ?? (!hasName && (section || page) ? current : undefined)
  if (!chosen) return undefined
  const passage = section ? chosen.sections.get(section.toLowerCase()) : undefined
  return {
    source: chosen,
    link: {
      documentId: chosen.documentId,
      title: chosen.title,
      section,
      page: passage?.page_start ?? (page ? Number(page) : undefined),
    },
  }
}


const BRACKET = /\[([^[\]]{2,160})\]/g

interface HastNode {
  type: string
  tagName?: string
  value?: string
  properties?: Record<string, unknown>
  children?: HastNode[]
}

/**
 * Rewrites resolvable citations into `<a href="cite:...">`, which the message
 * renders as a button. Written by hand rather than with unist-util-visit so
 * the app keeps its dependency list short.
 */
export function rehypeCiteLinks(sources: CiteSource[]) {
  return () => (tree: HastNode) => {
    if (!sources.length) return
    let current: CiteSource | undefined
    // Longest first: "Employment Code Act" must win over "Employment Act".
    const names = sources
      .flatMap((s) => s.keys.map((k) => ({ key: k, source: s })))
      .filter(({ key }) => key.length >= 6 && key.includes(' '))
      .sort((a, b) => b.key.length - a.key.length)

    const trackNames = (text: string, upto: number) => {
      const hay = norm(text.slice(0, upto))
      let last: { at: number; source: CiteSource } | undefined
      for (const { key, source } of names) {
        const at = hay.lastIndexOf(key)
        if (at >= 0 && at >= (last?.at ?? -1)) last = { at, source }
      }
      if (last) current = last.source
    }

    const splitText = (value: string): HastNode[] => {
      const out: HastNode[] = []
      let cursor = 0
      for (const m of value.matchAll(BRACKET)) {
        const at = m.index ?? 0
        trackNames(value, at)
        const resolved = resolveCite(m[1], sources, current)
        if (!resolved) continue
        current = resolved.source
        if (at > cursor) out.push({ type: 'text', value: value.slice(cursor, at) })
        out.push({
          type: 'element',
          tagName: 'a',
          properties: {
            // No href: react-markdown strips an unknown scheme, and a citation
            // opens the in-app viewer rather than navigating anywhere.
            'data-cite': resolved.link.documentId,
            'data-page': resolved.link.page ? String(resolved.link.page) : undefined,
            'data-title': resolved.link.title,
            className: ['cp-cite'],
          },
          children: [{ type: 'text', value: m[0] }],
        })
        cursor = at + m[0].length
      }
      if (!out.length) return [{ type: 'text', value }]
      trackNames(value, value.length)
      if (cursor < value.length) out.push({ type: 'text', value: value.slice(cursor) })
      return out
    }

    const walk = (node: HastNode) => {
      if (!node.children) return
      if (node.type === 'element' && ['a', 'code', 'pre'].includes(node.tagName || '')) return
      const out: HastNode[] = []
      for (const child of node.children) {
        if (child.type === 'text') out.push(...splitText(child.value || ''))
        else {
          walk(child)
          out.push(child)
        }
      }
      node.children = out
    }
    walk(tree)
  }
}
