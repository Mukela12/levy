import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import { AlertTriangle } from 'lucide-react'
import { listActs, getActBySlug, SITE_URL, SHARE_IMAGE } from '@/lib/server/corpus'

export const revalidate = 86400
export const dynamicParams = true

export async function generateStaticParams() {
  const acts = await listActs()
  return acts.map((a) => ({ slug: a.slug }))
}

function lead(name: string, year: number | null, sections: number): string {
  const yr = year ? ` enacted in ${year}` : ''
  const sec = sections > 0 ? ` It contains ${sections} sections.` : ''
  return `The ${name} is an Act of the Parliament of Zambia${yr}.${sec} Read its sections below, or ask Levy any question about the ${name} and get an answer grounded in the Act with citations.`
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params
  const act = await getActBySlug(slug)
  if (!act) return { title: 'Act not found | Levy' }
  // Someone landing here from a search should learn it is repealed in the
  // result itself, not after reading the Act.
  const repealed = act.status?.status === 'repealed'
  const desc = repealed
    ? `${act.name}: a REPEALED Zambian Act${act.status?.repealedBy.length ? `, replaced by ${act.status.repealedBy[0]}` : ''}. Read its sections for the law as it stood, and ask Levy what applies now.`
    : `${act.name}${act.year ? ` (${act.year})` : ''}: a Zambian Act of Parliament. Browse its sections and ask Levy questions answered with citations to the legislation.`
  return {
    title: `${act.name}${act.year ? ` (${act.year})` : ''} | Zambian Law`,
    description: desc.slice(0, 300),
    alternates: { canonical: `${SITE_URL}/acts/${act.slug}` },
    openGraph: { title: `${act.name} | Zambian Law`, description: desc.slice(0, 300), url: `${SITE_URL}/acts/${act.slug}`, images: [SHARE_IMAGE] },
  }
}

export default async function ActPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const act = await getActBySlug(slug)
  if (!act) notFound()
  // The Act that repealed this one, so the reader can go straight to the law
  // that replaced it instead of reading a dead Act.
  const replacement = act.status?.repealedById
    ? (await listActs()).find((a) => a.id === act.status!.repealedById)
    : undefined

  const url = `${SITE_URL}/acts/${act.slug}`
  const jsonLd = {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Legislation',
        name: act.name,
        legislationType: 'Act',
        legislationJurisdiction: 'Zambia',
        ...(act.actNumber ? { legislationIdentifier: act.actNumber } : {}),
        ...(act.year ? { datePublished: String(act.year) } : {}),
        inLanguage: 'en',
        url,
        publisher: { '@type': 'GovernmentOrganization', name: 'Parliament of Zambia' },
      },
      {
        '@type': 'BreadcrumbList',
        itemListElement: [
          { '@type': 'ListItem', position: 1, name: 'Acts', item: `${SITE_URL}/acts` },
          { '@type': 'ListItem', position: 2, name: act.name, item: url },
        ],
      },
    ],
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />

      <nav className="text-[12px] text-white/40 mb-4">
        <Link href="/acts" className="hover:text-emerald-300">Acts</Link>
        <span className="mx-1.5">/</span>
        <span className="text-white/55">{act.name}</span>
      </nav>

      <h1 className="text-[26px] font-semibold text-white/90 tracking-tight leading-snug">
        {act.name}
      </h1>
      <div className="flex flex-wrap gap-2 mt-2.5">
        <span className="px-2 py-0.5 rounded text-[11px] bg-white/[0.05] border border-white/[0.08] text-white/55">Zambia</span>
        <span className="px-2 py-0.5 rounded text-[11px] bg-white/[0.05] border border-white/[0.08] text-white/55">Act of Parliament</span>
        {act.year ? <span className="px-2 py-0.5 rounded text-[11px] bg-white/[0.05] border border-white/[0.08] text-white/55">{act.year}</span> : null}
        {act.actNumber ? <span className="px-2 py-0.5 rounded text-[11px] bg-white/[0.05] border border-white/[0.08] text-white/55">No. {act.actNumber}</span> : null}
      </div>

      {act.status?.status === 'repealed' && (
        <div className="cp-act-notice" role="note">
          <AlertTriangle size={16} aria-hidden="true" style={{ flexShrink: 0, marginTop: 2 }} />
          <div>
            <strong>This Act has been repealed.</strong>
            {replacement ? (
              <>It was replaced by <Link href={`/acts/${replacement.slug}`}>{replacement.name}</Link>. Read this one for the law as it stood, not as it is now.</>
            ) : act.status.repealedBy.length ? (
              <>It was replaced by {act.status.repealedBy.join(', ')}. Read this one for the law as it stood, not as it is now.</>
            ) : (
              <>It is no longer in force. Read it for the law as it stood, not as it is now.</>
            )}
          </div>
        </div>
      )}
      {act.status?.status !== 'repealed' && (act.status?.amendments ?? 0) > 0 && (
        <p className="cp-act-amended">
          In force, and amended by {act.status!.amendments} amendment Act{act.status!.amendments === 1 ? '' : 's'}.
          Check the amendments before relying on the wording of a section.
        </p>
      )}

      <p className="text-[14.5px] text-white/65 mt-4 leading-relaxed">
        {lead(act.name, act.year, act.sectionList.length || act.sections)}
      </p>

      <div className="mt-5 flex flex-wrap gap-2.5">
        <Link
          href={`/chat?q=${encodeURIComponent(`Explain the ${act.name} in plain language and cite the key sections.`)}`}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-[13.5px] font-medium bg-emerald-500/15 border border-emerald-500/30 text-emerald-100 hover:bg-emerald-500/25 transition-colors"
        >
          Ask Levy about this Act →
        </Link>
        <Link
          href={`/chat?q=${encodeURIComponent(`Make me an exam cheat sheet on the ${act.name}.`)}`}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-[13.5px] font-medium text-white/70 border border-white/[0.10] hover:bg-white/[0.04] transition-colors"
        >
          Make a cheat sheet
        </Link>
      </div>

      {act.sectionList.length > 0 && (
        <section className="mt-9">
          <h2 className="text-[13px] uppercase tracking-wider text-emerald-300/70 mb-3">
            Sections of the {act.name}
          </h2>
          <ul className="space-y-0.5">
            {act.sectionList.map((s) => (
              <li key={s.number}>
                <Link
                  href={`/chat?q=${encodeURIComponent(`What does section ${s.number} of the ${act.name} say?`)}`}
                  className="group flex items-baseline gap-3 py-1.5 px-2 -mx-2 rounded-lg hover:bg-white/[0.03]"
                >
                  <span className="text-[12px] text-emerald-400/60 font-medium tabular-nums shrink-0 w-12">S. {s.number}</span>
                  <span className="text-[13.5px] text-white/75 group-hover:text-emerald-200">
                    {s.title || `Section ${s.number}`}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="mt-10 pt-6 border-t border-white/[0.06]">
        <Link href="/acts" className="text-[13px] text-white/45 hover:text-emerald-300">← All Zambian Acts</Link>
      </div>
    </div>
  )
}
