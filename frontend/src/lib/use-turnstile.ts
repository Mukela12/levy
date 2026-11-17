'use client'

import { useEffect, useState, useSyncExternalStore } from 'react'
import { createTurnstileCheck, type CheckEnv } from './turnstile-check'

// Cloudflare Turnstile, used to let signed-out visitors try Levy without an
// account. Anonymous chat was hard-disabled after a distributed flood used
// browser-like user-agents across many IPs. Turnstile tokens are single-use,
// so the FIRST anonymous question costs one solved challenge; the server then
// issues a pass bound to the visitor's IP that covers the rest of the visit.
//
// It does not load on arrival: Cloudflare's script and challenge are ~600KB, a
// quarter of a first visit on mobile data, spent before anyone has typed. The
// page calls prime() when a question starts (typing, a suggestion, In Focus),
// which leaves the typing time for the solve; getToken() loads it on demand
// for anyone who sends first.
//
// The logic lives in turnstile-check.ts (tested in node); this hook only
// connects it to React. `card` says what the on-screen check card shows:
// nothing, "checking", "tick the box", or "failed" with a way forward.
//
// The site key is public by design. If it is unset the hook reports
// `enabled: false`, the UI keeps asking people to sign in, and the backend
// independently refuses anonymous chat — both ends fail closed.

const SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || ''
const SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'

// Read lazily: the check only touches the page from effects and event
// handlers, so creating it during a server render is harmless.
const browserEnv: CheckEnv = {
  get win() {
    return window as unknown as CheckEnv['win']
  },
  get doc() {
    return document as unknown as CheckEnv['doc']
  },
  setTimeout: (fn, ms) => window.setTimeout(fn, ms),
  clearTimeout: (h) => window.clearTimeout(h as number),
  now: () => Date.now(),
}

export function useTurnstile(active: boolean) {
  const [c] = useState(() => createTurnstileCheck(SITE_KEY, SCRIPT_SRC, browserEnv))
  const view = useSyncExternalStore(c.subscribe, c.getView, c.getView)

  const enabled = active && !!SITE_KEY
  useEffect(() => {
    c.setEnabled(enabled)
    return () => c.setEnabled(false)
  }, [c, enabled])

  return {
    holderRef: c.setHolder,
    enabled,
    ready: view.ready,
    showing: view.showing,
    card: view.card,
    reason: view.reason,
    prime: c.prime,
    getToken: c.getToken,
    restart: c.restart,
    fail: c.fail,
    dismiss: c.dismiss,
    lastError: c.lastError,
  }
}
