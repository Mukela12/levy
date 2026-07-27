'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

// Cloudflare Turnstile, used to let signed-out visitors try Levy without an
// account. Anonymous chat was hard-disabled after a distributed flood used
// browser-like user-agents across many IPs; Turnstile issues a SINGLE-USE
// token per request, so each anonymous question costs one solved challenge,
// which is the part per-IP limits could never do.
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

  const enabled = active && !!SITE_KEY

  // Deliver a token to whoever is waiting, or bank it for the next getToken().
  const deliver = useCallback((t: string | null) => {
    if (waiterRef.current) {
      const w = waiterRef.current
      waiterRef.current = null
      w(t)
    } else {
      tokenRef.current = t
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    let cancelled = false

    const render = () => {
      if (cancelled || widgetId.current || !holderRef.current || !window.turnstile) return
      try {
        widgetId.current = window.turnstile.render(holderRef.current, {
          sitekey: SITE_KEY,
          // Only shows a visible challenge when Cloudflare wants interaction;
          // otherwise it stays out of the way.
          appearance: 'interaction-only',
          callback: (t: string) => deliver(t),
          'error-callback': () => deliver(null),
          'expired-callback': () => deliver(null),
          'timeout-callback': () => deliver(null),
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
  }, [enabled, deliver])

  /**
   * Resolve a fresh single-use token, then immediately arm the widget for the
   * next question. Resolves null (rather than hanging) if the challenge fails
   * or takes too long — the caller then falls back to asking for sign-in.
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
        window.turnstile.reset(id)
        return true
      } catch {
        // The widget was torn down (e.g. its host div unmounted).
        return false
      }
    }

    // A token banked by the initial solve is used first.
    if (tokenRef.current) {
      const t = tokenRef.current
      tokenRef.current = null
      armNext()
      return t
    }

    return new Promise<string | null>((resolve) => {
      const timer = setTimeout(() => {
        waiterRef.current = null
        resolve(null)
      }, 15000)
      waiterRef.current = (t) => {
        clearTimeout(timer)
        resolve(t)
      }
      // Nothing banked: ask the widget for a new one. If there is no live
      // widget, fail fast instead of waiting out the timeout.
      if (!armNext()) {
        clearTimeout(timer)
        waiterRef.current = null
        resolve(null)
      }
    })
  }, [enabled])

  return { holderRef, ready, enabled, getToken }
}
