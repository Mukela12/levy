/**
 * Telling a lost connection apart from a server error. Phones lose signal
 * often (Levy's users are mostly on Zambian mobile data), and "Sorry, I
 * encountered an error" sends them looking for a fault that is really a
 * dropped connection.
 */
const OFFLINE = "You're offline."
const UNREACHABLE = "Levy couldn't be reached. Check your connection."
const RESTORED = ' Your question is back in the box below: send it again when you are connected.'
const RETRY = ' Send your question again when you are connected.'

// Android's WebView keeps navigator.onLine true in airplane mode, so the app
// feeds in the native status (Capacitor Network, see AppShell). The website
// has only the browser's flag.
let nativeConnected: boolean | null = null
export function setNativeConnected(connected: boolean | null) {
  nativeConnected = connected
}

export function isOffline(): boolean {
  if (nativeConnected !== null) return !nativeConnected
  return typeof navigator !== 'undefined' && navigator.onLine === false
}

/**
 * fetch() rejects with a TypeError whose message names the network when the
 * request never reached a server (Chrome "Failed to fetch", Safari "Load
 * failed"). Other TypeErrors are bugs, not lost signal, so the message decides.
 */
export function isNetworkError(e: unknown): boolean {
  // Supabase hands back a plain error object, not an Error, with the fetch
  // failure in its message ("TypeError: Failed to fetch").
  const message =
    e instanceof Error ? e.message
      : e && typeof e === 'object' && typeof (e as { message?: unknown }).message === 'string' ? (e as { message: string }).message
        : ''
  return /failed to fetch|networkerror|network request failed|load failed|fetch failed|network connection was lost|internet connection appears to be offline/i.test(message)
}

/**
 * The message for a failed question, or null when it isn't a connection
 * problem. `restored` says whether the caller put the question back in the
 * composer, so the message never promises what didn't happen.
 */
export function connectionMessage(e: unknown, restored = false): string | null {
  const tail = restored ? RESTORED : RETRY
  if (isOffline()) return OFFLINE + tail
  if (isNetworkError(e)) return UNREACHABLE + tail
  return null
}
