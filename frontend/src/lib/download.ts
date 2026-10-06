/**
 * Getting a generated document onto a phone.
 *
 * The only thumbs-down Levy has ever had came from a citizen on a phone, at
 * night, drafting detention-complaint letters: Download did nothing, four
 * times, and they left for ChatGPT. The legal content was fine. The old path
 * awaited two network round trips and then clicked a target="_blank" link; by
 * then the tap no longer counted as a user gesture, so mobile browsers treated
 * the new tab as a popup and blocked it without an error, and the fallback
 * never showed.
 *
 * Rules that matter:
 *  - A prefetched signed URL is used as a real link, tapped by the user.
 *  - Otherwise the file is opened in the SAME tab. Storage answers with
 *    Content-Disposition: attachment (the `download` query parameter), so the
 *    browser saves the file and Levy stays on screen. Same-tab navigation is
 *    never popup-blocked.
 *  - In-app browsers (Facebook, Instagram, LinkedIn, Android webviews) often
 *    cannot save files at all; say so and lead with the copyable text.
 */

/** Ask Supabase Storage to serve the file as an attachment, not inline. */
export function withDownloadParam(url: string, filename: string): string {
  try {
    const u = new URL(url)
    u.searchParams.set('download', filename)
    return u.toString()
  } catch {
    return url
  }
}

/** A filename every phone accepts: no slashes, colons or control characters. */
export function filenameFor(title: string, ext: 'pdf' | 'docx'): string {
  const base = (title || 'Levy document')
    .replace(/[\u0000-\u001f\u007f]/g, '')
    .replace(/[\\/:*?"<>|#%]+/g, '-')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 80)
    .replace(/[\s.-]+$/, '')
  return `${base || 'Levy document'}.${ext}`
}

/** Facebook, Instagram, LinkedIn, TikTok, Line and Android WebViews. */
const IN_APP = /\bFBAN\/|\bFBAV\/|\bInstagram\b|\bLinkedInApp\b|\bmusical_ly\b|\bBytedanceWebview\b|\bLine\/|;\s*wv\)/

export function isInAppBrowser(userAgent: string | undefined | null): boolean {
  return IN_APP.test(userAgent || '')
}

/** Signed URLs are issued for an hour; treat them as stale well before that. */
export const LINK_TTL_MS = 45 * 60 * 1000

export interface CachedLink {
  url: string
  at: number
}

export function isFresh(link: CachedLink | undefined, now: number): link is CachedLink {
  return Boolean(link && link.url && now - link.at < LINK_TTL_MS)
}
