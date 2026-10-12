'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

// Cloudflare Turnstile, used to let signed-out visitors try Levy without an
// account. Anonymous chat was hard-disabled after a distributed flood used
// browser-like user-agents across many IPs. Turnstile tokens are single-use,
// so the FIRST anonymous question costs one solved challenge; the server then
// issues a pass bound to the visitor's IP that covers the rest of the visit.
//
// This hook used to re-arm the widget the moment a token was spent, so the
// checkbox reappeared while the first answer was still streaming, and again
// after the last free question. It now only asks Cloudflare for a token when a
// caller actually needs one.
//
// Nor does it load on arrival: Cloudflare's script and challenge are ~600KB, a
// quarter of a first visit on mobile data, spent before anyone has typed. The
// page calls prime() when a question starts (typing, a suggestion, In Focus),
// which leaves the typing time for the solve; getToken() loads it on demand
// for anyone who sends first.
//
// The site key is public by design. If it is unset the hook reports
// `enabled: false`, the UI keeps asking people to sign in, and the backend
// independently refuses anonymous chat — both ends fail closed.

const SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || ''
const SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'

type TurnstileApi = {
  render: (el: HTMLElement, opts: Record<string, unknown>) => string
  reset: (id: string) => void
  remove: (id: string) => void
}
declare global {
  interface Window {
    turnstile?: TurnstileApi
  }
}

export function useTurnstile(active: boolean) {
  const holderRef = useRef<HTMLDivElement | null>(null)
  const widgetId = useRef<string | null>(null)
  const tokenRef = useRef<string | null>(null)
  const waiterRef = useRef<((t: string | null) => void) | null>(null)
  const [ready, setReady] = useState(false)
  // Whether the widget may draw. Hidden once a token is in hand, so a solved
  // widget does not sit over the composer; shown again only for a new ask.
  const [showing, setShowing] = useState(true)
  const [wanted, setWanted] = useState(false)
  // After a failed check the widget is rebuilt and drawn whether or not
  // Cloudflare asks for interaction, so a challenge that wants a click is on
  // screen instead of hidden. `generation` forces the rebuild.
  const [visible, setVisible] = useState(false)
  const [generation, setGeneration] = useState(0)
  // Why the last attempt produced no token: the widget's error code,
  // "challenge_timeout", "expired", "timeout" or "no_widget". Sent with a
  // failed request so the server log can say why a visitor was turned away.
  const lastErrorRef = useRef<string | null>(null)

  const enabled = active && !!SITE_KEY
  const prime = useCallback(() => setWanted(true), [])

  // Deliver a token to whoever is waiting, or bank it for the next getToken().
  const deliver = useCallback((t: string | null) => {
    if (t) setShowing(false)
    if (waiterRef.current) {
      const w = waiterRef.current
      waiterRef.current = null
      w(t)
    } else {
      tokenRef.current = t
    }
  }, [])

  useEffect(() => {
    if (!enabled || !wanted) return
    let cancelled = false

    const render = () => {
      if (cancelled || widgetId.current || !holderRef.current || !window.turnstile) return
      try {
        widgetId.current = window.turnstile.render(holderRef.current, {
          sitekey: SITE_KEY,
          // Only shows a visible challenge when Cloudflare wants interaction;
          // otherwise it stays out of the way.
          appearance: visible ? 'always' : 'interaction-only',
          // A banked token expires after 5 minutes. Auto-refresh would pop a
          // fresh challenge while someone is only reading; getToken() asks for
          // a new one if and when it is actually needed.
          'refresh-expired': 'never',
          callback: (t: string) => {
            lastErrorRef.current = null
            deliver(t)
          },
          'error-callback': (code?: string | number) => {
            lastErrorRef.current = code ? String(code) : 'error'
            deliver(null)
          },
          'expired-callback': () => {
            lastErrorRef.current = 'expired'
            deliver(null)
          },
          'timeout-callback': () => {
            lastErrorRef.current = 'challenge_timeout'
            deliver(null)
          },
        })
        setReady(true)
      } catch {
        setReady(false)
      }
    }

    if (window.turnstile) {
      render()
    } else {
      const existing = document.querySelector<HTMLScriptElement>(
        'script[src^="https://challenges.cloudflare.com/turnstile/v0/api.js"]',
      )
      if (existing) {
        existing.addEventListener('load', render)
      } else {
        const s = document.createElement('script')
        s.src = SCRIPT_SRC
        s.async = true
        s.defer = true
        s.onload = render
        document.head.appendChild(s)
      }
    }

    return () => {
      cancelled = true
      const id = widgetId.current
      widgetId.current = null
      if (id && window.turnstile) {
        try {
          window.turnstile.remove(id)
        } catch {
          // widget already gone
        }
      }
    }
  }, [enabled, wanted, deliver, visible, generation])

  /** Start again with a fresh widget, drawn visibly. */
  const restart = useCallback(() => {
    const id = widgetId.current
    widgetId.current = null
    tokenRef.current = null
    if (id && window.turnstile) {
      try {
        window.turnstile.remove(id)
      } catch {
        // widget already gone
      }
    }
    setVisible(true)
    setShowing(true)
    setWanted(true)
    setGeneration((g) => g + 1)
  }, [])

  const lastError = useCallback(() => lastErrorRef.current, [])

  /**
   * Resolve a single-use token: the one banked by the initial solve if there
   * is one, otherwise a fresh challenge. Resolves null (rather than hanging)
   * if the challenge fails or takes too long; the caller then shows the
   * server's "could not verify" message.
   */
  const getToken = useCallback(async (): Promise<string | null> => {
    if (!enabled) return null

    // Ask the widget for a new token. Returns false if there is no live widget
    // to ask — the caller must not then sit waiting for a callback that can
    // never fire.
    const armNext = (): boolean => {
      const id = widgetId.current
      if (!id || !window.turnstile) return false
      try {
        setShowing(true)
        window.turnstile.reset(id)
        return true
      } catch {
        // The widget was torn down (e.g. its host div unmounted).
        return false
      }
    }

    // A token banked by the initial solve is used first. Deliberately NOT
    // re-arming here: the server's pass covers later questions, and a reset
    // now is what made the checkbox reappear mid-answer.
    if (tokenRef.current) {
      const t = tokenRef.current
      tokenRef.current = null
      return t
    }

    lastErrorRef.current = null
    return new Promise<string | null>((resolve) => {
      // Longer than a solve alone: a send before prime() also waits for
      // Cloudflare's script (~600KB) to download, which on mobile data in
      // Zambia can take most of 20 seconds by itself.
      const timer = setTimeout(() => {
        waiterRef.current = null
        lastErrorRef.current = lastErrorRef.current ?? 'timeout'
        resolve(null)
      }, 30000)
      waiterRef.current = (t) => {
        clearTimeout(timer)
        resolve(t)
      }
      // Not loaded yet: load it now, and its first solve resolves this wait.
      if (!widgetId.current) {
        setWanted(true)
        return
      }
      // Nothing banked: ask the widget for a new one. If there is no live
      // widget, fail fast instead of waiting out the timeout.
      if (!armNext()) {
        clearTimeout(timer)
        waiterRef.current = null
        lastErrorRef.current = 'no_widget'
        resolve(null)
      }
    })
  }, [enabled])

  return { holderRef, ready, enabled, showing, prime, getToken, restart, lastError }
}
