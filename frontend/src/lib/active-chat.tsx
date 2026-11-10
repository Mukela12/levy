'use client'

import { Suspense, useEffect, useSyncExternalStore } from 'react'
import { usePathname, useSearchParams } from 'next/navigation'
import { IS_APP, activeChatId } from './routes'

// In the app build the open chat is in the query string (see routes.ts).
// Reading it needs useSearchParams, which would turn every page that shows the
// sidebar into a client-only render during the static export. One probe,
// mounted once in its own Suspense boundary, keeps that cost to itself and
// shares the id through a tiny store.

let current: string | null = null
const listeners = new Set<() => void>()

function publish(id: string | null) {
  if (id === current) return
  current = id
  listeners.forEach((l) => l())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

function Probe() {
  const pathname = usePathname()
  const search = useSearchParams()
  const id = activeChatId(pathname, search.toString())
  useEffect(() => { publish(id) }, [id])
  return null
}

/** Mount once in the dashboard layout. Renders nothing on the web. */
export function ActiveChatProbe() {
  return IS_APP ? <Suspense fallback={null}><Probe /></Suspense> : null
}

/** The id of the chat on screen, or null. */
export function useActiveChatId(): string | null {
  const pathname = usePathname()
  const fromQuery = useSyncExternalStore(subscribe, () => current, () => null)
  return IS_APP ? fromQuery : activeChatId(pathname)
}

// A conversation can be on screen before it has an id: the first question is
// shown at once while the chat is still being saved. The conversation view
// registers itself here so the shell can switch to its chat layout without
// waiting for the saved route.
let conversations = 0
const conversationListeners = new Set<() => void>()

function subscribeConversation(listener: () => void) {
  conversationListeners.add(listener)
  return () => { conversationListeners.delete(listener) }
}

/** Call from the conversation view: marks a conversation as on screen while mounted. */
export function useRegisterConversation() {
  useEffect(() => {
    conversations += 1
    conversationListeners.forEach((l) => l())
    return () => {
      conversations -= 1
      conversationListeners.forEach((l) => l())
    }
  }, [])
}

/** True while a conversation (saved or not yet saved) is on screen. */
export function useConversationShowing(): boolean {
  return useSyncExternalStore(subscribeConversation, () => conversations > 0, () => false)
}
