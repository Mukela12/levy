import type { Metadata } from 'next'
import Link from 'next/link'
import { listActs, SITE_URL } from '@/lib/server/corpus'

export const revalidate = 86400 // refresh daily

export const metadata: Metadata = {
  title: 'Acts of Parliament of Zambia',
  description:
    'Browse the Acts of Parliament of Zambia. Read what each Act covers, jump to any section, and ask Levy questions answered with citations to the legislation.',
  alternates: { canonical: `${SITE_URL}/acts` },
  openGraph: {
    title: 'Zambian Acts of Parliament — Full List',
    description: 'Browse and search the Acts of Parliament of Zambia, with AI answers grounded in the legislation.',
    url: `${SITE_URL}/acts`,
  },
}

export default async function ActsIndex() {
  const acts = await listActs()
  // group alphabetically for scannability
  const groups = new Map<string, typeof acts>()
  for (const a of acts) {
    const k = /[a-z]/i.test(a.name[0]) ? a.name[0].toUpperCase() : '#'
    if (!groups.has(k)) groups.set(k, [])
    groups.get(k)!.push(a)
  }
  const letters = [...groups.keys()].sort()

  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <h1 className="text-[26px] font-semibold text-white/90 tracking-tight">
        Acts of Parliament of Zambia
      </h1>
      <p className="text-[14px] text-white/55 mt-2 leading-relaxed">
        {`A directory of ${acts.length} Zambian Acts in Levy's library. Open any Act to see its sections, or ask Levy a question and get an answer grounded in the legislation with citations. Free to use.`}
      </p>

      <div className="mt-6">
        <Link
          href="/chat"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-[13.5px] font-medium bg-emerald-500/15 border border-emerald-500/30 text-emerald-100 hover:bg-emerald-500/25 transition-colors"
        >
          Ask a question about Zambian law →
        </Link>
      </div>

      <nav className="flex flex-wrap gap-1.5 mt-8 mb-6" aria-label="Jump to letter">
        {letters.map((l) => (
          <a key={l} href={`#${l}`} className="px-2 py-0.5 rounded text-[12px] text-white/45 hover:text-emerald-300 border border-white/[0.06]">
            {l}
          </a>
        ))}
      </nav>

      <div className="space-y-7">
        {letters.map((l) => (
          <section key={l} id={l}>
            <h2 className="text-[12px] uppercase tracking-wider text-emerald-300/70 mb-2">{l}</h2>
            <ul className="space-y-0.5">
              {groups.get(l)!.map((a) => (
                <li key={a.slug}>
                  <Link
                    href={`/acts/${a.slug}`}
                    className="group flex items-baseline justify-between gap-3 py-1.5 px-2 -mx-2 rounded-lg hover:bg-white/[0.03]"
                  >
                    <span className="text-[14px] text-white/80 group-hover:text-emerald-200">
                      {a.name}
                      {a.year ? <span className="text-white/35"> ({a.year})</span> : null}
                    </span>
                    {a.sections > 0 && (
                      <span className="text-[11px] text-white/30 shrink-0">{a.sections} sections</span>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  )
}
