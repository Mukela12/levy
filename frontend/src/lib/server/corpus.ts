/**
 * Server-only corpus reader for the public, SEO-facing content pages
 * (/acts, sitemap, llms.txt). The global library is public-read by anon RLS,
 * so we query Supabase directly with the anon key at build / revalidate time.
 * No service key, no backend round-trip.
 */
import 'server-only'
import { createClient } from '@supabase/supabase-js'

export const SITE_URL = 'https://levylegal.ai'

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

export interface ActSummary {
  id: string
  slug: string
  name: string
  year: number | null
  actNumber: string | null
  sections: number
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
  const seen = new Map<string, number>()
  const acts: ActSummary[] = []
  // Sort by id first so collision suffixes are deterministic across builds.
  for (const r of [...rows].sort((a, b) => (a.id < b.id ? -1 : 1))) {
    const name = cleanName(r.title, r.short_name)
    let slug = slugify(name)
    const n = seen.get(slug) || 0
    seen.set(slug, n + 1)
    if (n > 0) slug = `${slug}-${r.act_number || r.year || n + 1}`
    acts.push({
      id: r.id, slug, name,
      year: r.year ?? null,
      actNumber: r.act_number ?? null,
      sections: r.total_sections || 0,
    })
  }
  acts.sort((a, b) => a.name.localeCompare(b.name))
  _memo = { at: Date.now(), acts }
  return acts
}

export async function getActBySlug(slug: string): Promise<ActDetail | null> {
  const acts = await listActs()
  const act = acts.find((a) => a.slug === slug)
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
        title: String(m.section_title ?? '').trim(),
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
