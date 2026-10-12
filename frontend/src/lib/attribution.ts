// Where a visitor came from, kept in their browser until they sign up.
//
// Levy could not tell which channel brought its users: the boosted LinkedIn
// post of 15 Sep 2026 counted 10 link clicks while 7 people signed up that
// week, two of whom became its most active users. The UTM tags, the referring
// site (its domain only) and the landing page are kept here; at signup they are
// saved with the account (user metadata `signup_source`), and an anonymous
// question carries the same summary so guests can be counted per channel too.
// Nothing here identifies a person.

const FIRST = 'levy-attribution-first'
const LAST = 'levy-attribution-last'
const UTM = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'] as const

export interface Touch {
  utm_source?: string
  utm_medium?: string
  utm_campaign?: string
  utm_content?: string
  utm_term?: string
  /** The referring site's domain, only when it is another site. */
  ref_host?: string
  /** Path of the page the visit began on, without its query. */
  landing?: string
  /** Day of the visit, YYYY-MM-DD. */
  at?: string
  /** A first visit with no tags and no outside referrer. */
  direct?: boolean
}

function clip(value: string | null | undefined, max = 100): string | undefined {
  const s = (value ?? '').replace(/[\u0000-\u001f]/g, '').trim()
  return s ? s.slice(0, max) : undefined
}

const bare = (host: string) => host.toLowerCase().replace(/^www\./, '')

/** The tags and outside referrer of one page load, or null for a direct or internal visit. */
export function readTouch(href: string, referrer: string, today = new Date()): Touch | null {
  let url: URL
  try {
    url = new URL(href)
  } catch {
    return null
  }
  const touch: Touch = {}
  for (const key of UTM) {
    const value = clip(url.searchParams.get(key))
    if (value) touch[key] = value
  }
  if (referrer) {
    try {
      const ref = new URL(referrer)
      if (ref.hostname && bare(ref.hostname) !== bare(url.hostname)) touch.ref_host = clip(bare(ref.hostname), 80)
    } catch {
      // an unreadable referrer says nothing
    }
  }
  if (!touch.utm_source && !touch.utm_campaign && !touch.ref_host) return null
  touch.landing = clip(url.pathname, 120)
  touch.at = today.toISOString().slice(0, 10)
  return touch
}

/** Keep this page load's source: the first one ever, and the latest tagged one. */
export function captureAttribution(): void {
  try {
    const touch = readTouch(window.location.href, document.referrer)
    if (!touch) {
      if (!localStorage.getItem(FIRST)) {
        const direct: Touch = { direct: true, landing: clip(window.location.pathname, 120), at: new Date().toISOString().slice(0, 10) }
        localStorage.setItem(FIRST, JSON.stringify(direct))
      }
      return
    }
    if (!localStorage.getItem(FIRST)) localStorage.setItem(FIRST, JSON.stringify(touch))
    localStorage.setItem(LAST, JSON.stringify(touch))
  } catch {
    // storage unavailable (private mode, blocked site data): nothing is kept
  }
}

/** What to save with a new account, or null when nothing was kept. */
export function getAttribution(): { first?: Touch; last?: Touch } | null {
  try {
    const first = JSON.parse(localStorage.getItem(FIRST) || 'null') as Touch | null
    const last = JSON.parse(localStorage.getItem(LAST) || 'null') as Touch | null
    if (!first && !last) return null
    return { ...(first ? { first } : {}), ...(last ? { last } : {}) }
  } catch {
    return null
  }
}

/** A short source for an anonymous question: the latest tagged visit, else the first. */
export function sourceSummary(): Record<string, string> | null {
  const kept = getAttribution()
  const touch = kept?.last ?? kept?.first
  if (!touch) return null
  const out: Record<string, string> = {}
  for (const key of ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'ref_host', 'landing'] as const) {
    const value = touch[key]
    if (typeof value === 'string' && value) out[key] = value
  }
  if (touch.direct) out.direct = 'true'
  return Object.keys(out).length ? out : null
}
