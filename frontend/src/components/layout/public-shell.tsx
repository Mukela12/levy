import Link from 'next/link'
import { LevyLogo } from '@/components/ui/levy-logo'

/**
 * Chrome for the public, indexable content pages (/acts, /answers). Not the
 * dashboard layout: no sidebar, no auth gate. Just a light header and a
 * cross-linked footer that funnels readers into the app and spreads internal
 * links across the SEO surface.
 */
export function PublicShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-full flex flex-col">
      <header className="border-b border-white/[0.06] sticky top-0 z-10 bg-background/80 backdrop-blur-sm">
        <div className="max-w-3xl mx-auto px-4 h-14 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2 text-foreground">
            <LevyLogo size={20} />
            <span className="font-semibold tracking-tight" style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}>
              Levy
            </span>
          </Link>
          <Link
            href="/chat"
            className="px-3.5 py-1.5 rounded-lg text-[13px] font-medium bg-emerald-500/15 border border-emerald-500/30 text-emerald-200 hover:bg-emerald-500/25 transition-colors"
          >
            Ask Levy
          </Link>
        </div>
      </header>

      <main className="flex-1">{children}</main>

      <footer className="border-t border-white/[0.06] mt-12">
        <div className="max-w-3xl mx-auto px-4 py-8 text-[12.5px] text-white/40 space-y-2">
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <Link href="/answers" className="hover:text-white/70">Common questions</Link>
            <Link href="/acts" className="hover:text-white/70">All Acts</Link>
            <Link href="/study" className="hover:text-white/70">Study mode</Link>
            <Link href="/chat" className="hover:text-white/70">Ask a question</Link>
          </div>
          <p>
            Levy is an AI legal assistant for Zambian law. It provides legal information grounded in
            published legislation, not legal advice. Always confirm with a qualified legal
            practitioner.
          </p>
        </div>
      </footer>
    </div>
  )
}
