import type { Metadata } from 'next'
import Link from 'next/link'
import { updates } from '@/lib/updates'

const SITE_URL = 'https://www.levylegal.ai'
const DESCRIPTION = 'What changed in Levy each month, and how to use it.'

export const metadata: Metadata = {
  title: 'Updates',
  description: DESCRIPTION,
  alternates: { canonical: `${SITE_URL}/updates` },
  openGraph: { title: 'Levy updates', description: DESCRIPTION, url: `${SITE_URL}/updates` },
}

export default function UpdatesPage() {
  return (
    <>
      <h1 className="lu-index-title">Updates</h1>
      <p className="lu-index-lede">{DESCRIPTION}</p>

      <ol className="lu-list" reversed>
        {updates.map((u) => (
          <li key={u.slug}>
            <Link href={`/updates/${u.slug}`} className="lu-entry">
              <span className="lu-month">{u.month}</span>
              <span className="lu-entry-title">{u.title}</span>
              <span className="lu-entry-summary">{u.summary}</span>
              <span className="lu-entry-more">Read the update</span>
            </Link>
          </li>
        ))}
      </ol>
    </>
  )
}
