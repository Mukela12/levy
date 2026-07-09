import type { Metadata } from 'next'
import Link from 'next/link'
import { answers, answersByCategory } from '@/lib/server/answers'
import { SITE_URL } from '@/lib/server/corpus'

export const metadata: Metadata = {
  title: 'Common Zambian Law Questions, Answered',
  description:
    'Clear answers to common questions about Zambian law: employment, company registration, land, divorce, succession, rights and more. Grounded in the Acts, with citations.',
  alternates: { canonical: `${SITE_URL}/answers` },
  openGraph: {
    title: 'Common Zambian Law Questions, Answered',
    description: 'Clear, cited answers to common Zambian legal questions. Free, and you can keep asking Levy.',
    url: `${SITE_URL}/answers`,
  },
}

export default function AnswersIndex() {
  const groups = answersByCategory()
  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <h1 className="text-[26px] font-semibold text-white/90 tracking-tight">
        Common Zambian law questions
      </h1>
      <p className="text-[14px] text-white/55 mt-2 leading-relaxed">
        {`Straight answers to ${answers.length} of the most-asked questions about Zambian law, grounded in the Acts with citations. Open any one to read the answer, then keep asking Levy your own follow-ups. Free to use.`}
      </p>

      <div className="mt-8 space-y-7">
        {groups.map(([cat, list]) => (
          <section key={cat}>
            <h2 className="text-[12px] uppercase tracking-wider text-emerald-300/70 mb-2">{cat}</h2>
            <ul className="space-y-0.5">
              {list.map((a) => (
                <li key={a.slug}>
                  <Link
                    href={`/answers/${a.slug}`}
                    className="block py-1.5 px-2 -mx-2 rounded-lg text-[14px] text-white/80 hover:text-emerald-200 hover:bg-white/[0.03]"
                  >
                    {a.question}
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
