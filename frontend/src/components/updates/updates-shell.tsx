import Link from 'next/link'
import Image from 'next/image'

/**
 * The frame of the updates pages: the Levy name at the top, a way into the
 * app, and the site's links at the foot. Light, like the app itself (the
 * older public pages under PublicShell are dark). Styles: styles/updates.css.
 */
export function UpdatesShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="lu-page">
      <header className="lu-top">
        <div className="lu-wrap">
          <Link href="/" className="lu-brand">
            {/* the green mark: the site's usual logo is drawn for a dark ground */}
            <Image src="/canopy/brand/levy-eagle.svg" alt="" width={30} height={30} unoptimized />
            <span>Levy</span>
          </Link>
          <Link href="/chat" className="lu-open">
            Open Levy
          </Link>
        </div>
      </header>

      <main className="lu-main">
        <div className="lu-wrap">{children}</div>
      </main>

      <footer className="lu-foot">
        <div className="lu-wrap">
          <nav aria-label="More of Levy">
            <Link href="/updates">Updates</Link>
            <Link href="/answers">Common questions</Link>
            <Link href="/acts">All Acts</Link>
            <Link href="/support">Help and support</Link>
            <Link href="/privacy">Privacy</Link>
          </nav>
          <p>Levy gives legal information, not legal advice. For anything you will file or sign, see a qualified lawyer.</p>
        </div>
      </footer>
    </div>
  )
}
