'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

interface BriefMessage {
  role: string
  content: string
}

interface BriefContextValue {
  messages: BriefMessage[]
  available: boolean
  open: boolean
  setOpen: (v: boolean) => void
  registerMessages: (messages: BriefMessage[], token?: string) => void
  token?: string
}

const BriefContext = createContext<BriefContextValue | null>(null)

export function BriefProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = useState<BriefMessage[]>([])
  const [token, setToken] = useState<string | undefined>(undefined)
  const [open, setOpen] = useState(false)

  // Keep registerMessages stable so consumers' effects don't refire each render.
  // Compare by length + last-content signature; we never need a deep equality
  // here because chat pages only mutate by appending or in-place token streaming.
  const registerMessages = useCallback((next: BriefMessage[], nextToken?: string) => {
    setMessages((prev) => {
      if (prev === next) return prev
      if (prev.length === next.length) {
        const lastA = prev[prev.length - 1]
        const lastB = next[next.length - 1]
        if (lastA?.content === lastB?.content && lastA?.role === lastB?.role) {
          return prev
        }
      }
      return next
    })
    setToken((prev) => (prev === nextToken ? prev : nextToken))
  }, [])

  const value = useMemo<BriefContextValue>(
    () => ({
      messages,
      available: messages.length > 0,
      open,
      setOpen,
      registerMessages,
      token,
    }),
    [messages, open, registerMessages, token],
  )

  return <BriefContext.Provider value={value}>{children}</BriefContext.Provider>
}

export function useBrief() {
  const ctx = useContext(BriefContext)
  if (!ctx) throw new Error('useBrief must be used within BriefProvider')
  return ctx
}

/**
 * Chat pages call this with their own messages state so the layout-level
 * Brief button + bottom sheet can read them. We deliberately accept the
 * caller's source array (NOT a `.map()` of it) so the effect's deps are
 * stable across renders - passing a fresh array each render would cause
 * an infinite render loop with the provider.
 */
export function useRegisterBrief(messages: BriefMessage[], token?: string) {
  const { registerMessages } = useBrief()

  useEffect(() => {
    registerMessages(messages, token)
  }, [messages, token, registerMessages])

  // Reset on unmount so a non-chat route does not keep stale data.
  useEffect(() => {
    return () => registerMessages([], undefined)
  }, [registerMessages])
}
