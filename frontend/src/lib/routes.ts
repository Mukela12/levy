/**
 * Where a saved chat or a matter lives, on the web and in the native app.
 *
 * The website has a server, so `/chat/<id>` is a real route. The iOS and
 * Android apps ship a static copy of the site (`LEVY_TARGET=app next build`)
 * with no server behind it, and a static export cannot answer a path it did
 * not build. In the app the id travels in the query string instead, on one
 * prebuilt page per kind: `/chat/view/?id=<id>`.
 *
 * Build every link with these helpers and read the open chat with
 * `activeChatId`, so neither build has to know about the other.
 */

export const IS_APP = process.env.NEXT_PUBLIC_LEVY_TARGET === 'app'

export function chatPath(id: string): string {
  return IS_APP ? `/chat/view/?id=${encodeURIComponent(id)}` : `/chat/${id}`
}

export function matterPath(id: string): string {
  return IS_APP ? `/matters/view/?id=${encodeURIComponent(id)}` : `/matters/${id}`
}

/**
 * The id of the chat on screen, or null on any other page.
 * `search` is `location.search` (or `useSearchParams().toString()`), read only
 * in the app build.
 */
export function activeChatId(pathname: string, search?: string | null): string | null {
  if (IS_APP) {
    if (!/^\/chat\/view\/?$/.test(pathname)) return null
    return new URLSearchParams(search ?? '').get('id')
  }
  return pathname.match(/^\/chat\/([^/]+)$/)?.[1] ?? null
}
