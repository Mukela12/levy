import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/**
 * One address for the live site.
 *
 * Vercel keeps `levy-ten.vercel.app` (and its two siblings) pointed at
 * production, and bots that ignore robots.txt crawl them: on 21 September
 * 2026 analytics recorded 4,490 visitors and a 98% bounce in a day, against
 * 3 guest visitors and 4 questions in the database over the same hours.
 * Every one of those hits loaded /chat once and left, which buries the real
 * numbers and spends the site's analytics and function budget.
 *
 * Production requests on any other host are sent to the canonical domain,
 * permanently, so a crawler follows the redirect and a person lands where
 * the cookies and the sign-in live. Preview deployments are left alone:
 * they have to answer on their own hostname to be reviewable.
 */
export const CANONICAL = 'www.levylegal.ai'

/** Whether this request should be sent to the canonical domain. */
export function sendToCanonical(host: string | null, vercelEnv: string | undefined): boolean {
  if (vercelEnv !== 'production') return false      // previews answer on their own host
  return Boolean(host) && host !== CANONICAL && (host || '').endsWith('.vercel.app')
}

export function proxy(request: NextRequest) {
  const host = request.headers.get('host') || ''
  if (sendToCanonical(host, process.env.VERCEL_ENV)) {
    const url = request.nextUrl.clone()
    url.host = CANONICAL
    url.protocol = 'https:'
    url.port = ''
    return NextResponse.redirect(url, 308)
  }
  // The chat app is not content. robots.txt already disallows it; this says
  // the same thing to a crawler that reads headers but not robots.
  if (request.nextUrl.pathname.startsWith('/chat')) {
    const response = NextResponse.next()
    response.headers.set('X-Robots-Tag', 'noindex, nofollow')
    return response
  }
  return NextResponse.next()
}

export const config = {
  // Everything except Next's own assets and the files crawlers must still read.
  matcher: ['/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml).*)'],
}
