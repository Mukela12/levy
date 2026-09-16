/**
 * Server-only corpus reader for the public, SEO-facing content pages
 * (/acts, sitemap, llms.txt). The global library is public-read by anon RLS,
 * so we query Supabase directly with the anon key at build / revalidate time.
 * No service key, no backend round-trip.
 */
import 'server-only'
import { createClient } from '@supabase/supabase-js'

export const SITE_URL = 'https://www.levylegal.ai'

// A page that sets its own openGraph replaces the root one, image included,
// so each of those pages passes the share image back in explicitly.
export const SHARE_IMAGE = {
  url: '/opengraph-image.png',
  width: 1200,
  height: 630,
  alt: 'Levy: Zambian law, plainly answered.',
}

function db() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { auth: { persistSession: false } },
  )
}

export function slugify(s: string): string {
  return (s || '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
}

/** Turn a messy corpus title into a clean, human display name. Some short_names
 *  are themselves the full SHOUTING title, so we always run the cleanup. */
export function cleanName(title: string, shortName?: string | null): string {
  const sn = (shortName || '').trim()
  let t = sn && sn.length > 3 && !/unknown/i.test(sn) ? sn : (title || '').trim()
  t = t
    .replace(/^REPUBLIC OF ZAMBIA\s+/i, '')
    .replace(/^THE\s+/i, '')
    .replace(/\s+/g, ' ')
    .trim()
  const letters = t.replace(/[^A-Za-z]/g, '')
  if (letters && letters === letters.toUpperCase()) {
    const SMALL = new Set(['a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'in', 'nor', 'of', 'on', 'or', 'the', 'to', 'with'])
    const titleToken = (w: string) => w.replace(/\b([a-z])/g, (_, c) => c.toUpperCase())
    t = t
      .toLowerCase()
      .split(' ')
      .map((w, i) => (i > 0 && SMALL.has(w) ? w : titleToken(w)))
      .join(' ')
  }
  return t || 'Untitled Act'
}

/** The year an Act was passed, read off its title when the column is empty.
 *  Prefers the year that follows "Act", so "Chapter 87 of the 1958 Edition of
 *  the Laws" does not date a 2019 Act to 1958. */
export function yearOf(title: string | null): number | null {
  const t = title || ''
  const after = t.match(/\bact\b[^0-9]{0,12}((?:18|19|20)\d{2})/i)
  if (after) return Number(after[1])
  const any = t.match(/\b((?:18|19|20)\d{2})\b/)
  return any ? Number(any[1]) : null
}

export interface ActSummary {
  id: string
  slug: string
  name: string
  year: number | null
  actNumber: string | null
  sections: number
  /** Present only when the Act is not simply in force. */
  status?: LawStatus
}

export interface LawStatus {
  status: string
  repealedBy: string[]
  repealedById: string | null
  amendments: number
}

/**
 * Repealed / amended status for library Acts, from the backend's law map.
 * A reader browsing the Acts should see what the model is told: the library
 * keeps repealed Acts beside the Acts that replaced them. Failure is silent,
 * because a missing badge is better than a legislation page that will not
 * render.
 */
let _statusMemo: { at: number; map: Record<string, LawStatus> } | null = null

export async function lawStatuses(): Promise<Record<string, LawStatus>> {
  if (_statusMemo && Date.now() - _statusMemo.at < TTL_MS) return _statusMemo.map
  try {
    const api = process.env.NEXT_PUBLIC_API_URL
    if (!api) return {}
    const res = await fetch(`${api}/api/law-map`, { signal: AbortSignal.timeout(10000), next: { revalidate: 21600 } })
    if (!res.ok) return _statusMemo?.map ?? {}
    const map = ((await res.json()) as { documents?: Record<string, LawStatus> }).documents ?? {}
    _statusMemo = { at: Date.now(), map }
    return map
  } catch {
    return _statusMemo?.map ?? {}
  }
}

/**
 * OCR of scanned Acts leaves some section headings as garbage ("Ti is Aci miy
 * b\u20ac cibd"). A heading that is mostly non-letters, or letter-salad with
 * broken words, reads worse than no heading: suppress it and let the page
 * fall back to "Section N".
 */
export function readableHeading(title: string): string {
  const t = title.trim()
  if (t.length < 4) return ''
  if (/[\u20ac$@#^~|<>{}\\]/.test(t)) return ''
  const tokens = t.split(/\s+/).map((w) => w.replace(/^[("'\u2018\u201c]+|[)"'\u2019\u201d.,;:!?]+$/g, ''))
  let vowelless = 0, considered = 0
  for (const w of tokens) {
    if (!w) return ''
    if (/\d/.test(w) && /[A-Za-z]/.test(w)) return ''
    if (/\./.test(w)) return ''
    if (w.length >= 2 && /^[A-Za-z]+$/.test(w)) {
      considered++
      if (!/[aeiouyAEIOUY]/.test(w)) vowelless++
    }
  }
  if (considered && vowelless / considered > 0.2) return ''
  return t
}

export interface ActSection {
  number: string
  title: string
  part: string | null
}

export interface ActDetail extends ActSummary {
  sectionList: ActSection[]
}

// Light module memo so 200+ page renders at build don't each re-fetch the
// whole act list. TTL keeps a long-lived server instance from going stale.
let _memo: { at: number; acts: ActSummary[] } | null = null
const TTL_MS = 60 * 60 * 1000

export async function listActs(): Promise<ActSummary[]> {
  if (_memo && Date.now() - _memo.at < TTL_MS) return _memo.acts
  const { data, error } = await db()
    .from('legal_documents')
    .select('id,title,short_name,year,act_number,total_sections,total_chunks')
    .eq('document_type', 'act')
    .eq('is_global', true)
  if (error) return _memo?.acts ?? []
  const rows = (data || []).filter((r) => (r.total_chunks || 0) > 1)
  // Sort by id first so collision suffixes are deterministic across builds.
  // The short_name usually drops the year the title carries, so the Companies
  // Act 2017 arrives as "Companies Act" and lands in the directory beside the
  // 1994 Act of the same name, one of them repealed. Rows that would be
  // indistinguishable keep their year, in the name and in the URL.
  const prepared = [...rows]
    .sort((a, b) => (a.id < b.id ? -1 : 1))
    .map((r) => ({ r, base: cleanName(r.title, r.short_name), year: r.year ?? yearOf(r.title) }))
  const nameCount = new Map<string, number>()
  for (const p of prepared) nameCount.set(p.base, (nameCount.get(p.base) || 0) + 1)

  const seen = new Map<string, number>()
  const acts: ActSummary[] = []
  for (const p of prepared) {
    const ambiguous = (nameCount.get(p.base) || 0) > 1
    const name = ambiguous && p.year && !p.base.includes(String(p.year))
      ? `${p.base}, ${p.year}`
      : p.base
    let slug = slugify(name)
    const n = seen.get(slug) || 0
    seen.set(slug, n + 1)
    if (n > 0) slug = `${slug}-${p.r.act_number || p.year || n + 1}`
    acts.push({
      id: p.r.id, slug, name,
      year: p.year,
      actNumber: p.r.act_number ?? null,
      sections: p.r.total_sections || 0,
    })
  }
  const statuses = await lawStatuses()
  for (const a of acts) {
    const s = statuses[a.id]
    if (s) a.status = s
  }
  acts.sort((a, b) => a.name.localeCompare(b.name))
  _memo = { at: Date.now(), acts }
  return acts
}

export async function getActBySlug(slug: string): Promise<ActDetail | null> {
  const acts = await listActs()
  // Dating an ambiguous Act moves its URL ("/acts/cotton-act" became
  // "/acts/cotton-act-2005" and "/acts/cotton-act-2025"). An old link should
  // land on the Act that is law today rather than on a 404.
  const act = acts.find((a) => a.slug === slug) ?? (() => {
    const kin = acts.filter((a) => a.slug.startsWith(`${slug}-`))
    if (!kin.length) return undefined
    const live = kin.filter((a) => a.status?.status !== 'repealed')
    return (live.length ? live : kin).sort((a, b) => (b.year ?? 0) - (a.year ?? 0))[0]
  })()
  if (!act) return null
  const { data } = await db()
    .from('legal_chunks')
    .select('metadata')
    .eq('document_id', act.id)
    .limit(3000)
  const map = new Map<string, ActSection>()
  for (const c of (data || []) as { metadata: Record<string, unknown> | null }[]) {
    const m = c.metadata || {}
    const number = String(m.section_number ?? '').trim()
    if (!number) continue
    if (!map.has(number)) {
      map.set(number, {
        number,
        title: readableHeading(String(m.section_title ?? '')),
        part: (m.part_number as string) || null,
      })
    }
  }
  const sectionList = [...map.values()].sort((a, b) => {
    const na = parseInt(a.number, 10)
    const nb = parseInt(b.number, 10)
    if (!isNaN(na) && !isNaN(nb)) return na - nb
    return a.number.localeCompare(b.number)
  })
  return { ...act, sectionList }
}
