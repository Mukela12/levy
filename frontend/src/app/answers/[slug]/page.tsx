import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Scale } from 'lucide-react'
import { answers, getAnswer } from '@/lib/server/answers'
import { listActs, cleanName, slugify, SITE_URL } from '@/lib/server/corpus'
import { AnswerFollowup } from '@/components/answers/answer-followup'

export const dynamicParams = false

export function generateStaticParams() {
  return answers.map((a) => ({ slug: a.slug }))
}

function plain(md: string): string {
  return md.replace(/[#*_>`\[\]]/g, '').replace(/\s+/g, ' ').trim()
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params
  const a = getAnswer(slug)
  if (!a) return { title: 'Question not found' }
  return {
    title: a.question,
    description: plain(a.answer).slice(0, 300),
    alternates: { canonical: `${SITE_URL}/answers/${a.slug}` },
    openGraph: { title: a.question, description: plain(a.answer).slice(0, 300), url: `${SITE_URL}/answers/${a.slug}` },
  }
}

export default async function AnswerPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const a = getAnswer(slug)
  if (!a) notFound()

  // resolve cited Acts to their /acts pages for internal linking
  const actList = await listActs()
  const bySlug = new Map(actList.map((x) => [x.slug, x]))
  const sources = a.sources.map((s) => {
    const actSlug = slugify(cleanName(s.act))
    const hit = bySlug.get(actSlug)
    return { ...s, name: hit?.name ?? cleanName(s.act), href: hit ? `/acts/${hit.slug}` : null }
  })
  const related = answers.filter((x) => x.category === a.category && x.slug !== a.slug).slice(0, 5)

  const url = `${SITE_URL}/answers/${a.slug}`
  const jsonLd = {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'QAPage',
        mainEntity: {
          '@type': 'Question',
          name: a.question,
          acceptedAnswer: { '@type': 'Answer', text: plain(a.answer) },
        },
      },
      {
        '@type': 'BreadcrumbList',
        itemListElement: [
          { '@type': 'ListItem', position: 1, name: 'Answers', item: `${SITE_URL}/answers` },
          { '@type': 'ListItem', position: 2, name: a.question, item: url },
        ],
      },
    ],
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />

      <nav className="text-[12px] text-white/40 mb-4">
        <Link href="/answers" className="hover:text-emerald-300">Answers</Link>
        <span className="mx-1.5">/</span>
        <span className="text-white/55">{a.category}</span>
      </nav>

      <h1 className="text-[24px] font-semibold text-white/90 tracking-tight leading-snug">{a.question}</h1>

      <article className="mt-5 text-[14.5px] leading-[1.75] text-white/75 [&_h2]:text-white/90 [&_h2]:text-[15px] [&_h2]:font-semibold [&_h2]:mt-5 [&_h2]:mb-1.5 [&_h3]:text-white/90 [&_h3]:text-[14px] [&_h3]:font-semibold [&_h3]:mt-4 [&_strong]:text-white/90 [&_li]:mb-1 [&_p]:mb-3 [&_ul]:list-disc [&_ul]:pl-5 [&_a]:text-emerald-300 [&_a]:underline">
        {/* Drop a leading "# Title" so we don't get a second H1 under the question,
            and downgrade any remaining headings a level. */}
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ h1: 'h2', h2: 'h3' }}>
          {a.answer.replace(/^\s*#\s+.+\n+/, '')}
        </ReactMarkdown>
      </article>

      {sources.length > 0 && (
        <div className="mt-7 rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
          <div className="flex items-center gap-1.5 text-[12px] uppercase tracking-wider text-emerald-300/70 mb-2.5">
            <Scale size={12} /> Sources
          </div>
          <ul className="space-y-1.5">
            {sources.map((s, i) => (
              <li key={i} className="text-[13px]">
                {s.href ? (
                  <Link href={s.href} className="text-white/80 hover:text-emerald-300">
                    {s.name}{s.section ? `, Section ${s.section}` : ''}
                  </Link>
                ) : (
                  <span className="text-white/70">{s.name}{s.section ? `, Section ${s.section}` : ''}</span>
                )}
              </li>
            ))}
          </ul>
          <p className="text-[11px] text-white/30 mt-3">
            Levy provides legal information, not legal advice. Confirm with a qualified legal practitioner.
          </p>
        </div>
      )}

      <AnswerFollowup question={a.question} />

      {related.length > 0 && (
        <section className="mt-10 pt-6 border-t border-white/[0.06]">
          <h2 className="text-[12px] uppercase tracking-wider text-white/40 mb-2.5">Related questions</h2>
          <ul className="space-y-0.5">
            {related.map((r) => (
              <li key={r.slug}>
                <Link href={`/answers/${r.slug}`} className="block py-1.5 text-[13.5px] text-white/70 hover:text-emerald-300">
                  {r.question}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="mt-8">
        <Link href="/answers" className="text-[13px] text-white/45 hover:text-emerald-300">← All questions</Link>
      </div>
    </div>
  )
}
