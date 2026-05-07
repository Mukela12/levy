'use client'

import { createContext, useContext, useEffect, useState } from 'react'

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

  function registerMessages(next: BriefMessage[], nextToken?: string) {
    setMessages(next)
    setToken(nextToken)
  }

  return (
    <BriefContext.Provider
      value={{
        messages,
        available: messages.length > 0,
        open,
        setOpen,
        registerMessages,
        token,
      }}
    >
      {children}
    </BriefContext.Provider>
  )
}

export function useBrief() {
  const ctx = useContext(BriefContext)
  if (!ctx) throw new Error('useBrief must be used within BriefProvider')
  return ctx
}

/** Helper hook: chat pages call this to push their messages into context. */
export function useRegisterBrief(messages: BriefMessage[], token?: string) {
  const { registerMessages } = useBrief()
  useEffect(() => {
    registerMessages(messages, token)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, token])

  // Reset on unmount so the next chat-less route doesn't keep the button.
  useEffect(() => {
    return () => registerMessages([], undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
