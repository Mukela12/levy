import type { Metadata } from 'next'
import { Newsreader } from 'next/font/google'

// Internal tools for Levy's editor. Never indexed, never linked from the app.
export const metadata: Metadata = {
  title: 'Levy editor',
  robots: { index: false, follow: false },
}

const newsreader = Newsreader({ subsets: ['latin'], variable: '--font-news', display: 'swap' })

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <div className={newsreader.variable}>{children}</div>
}
