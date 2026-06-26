'use client'

import { useEffect, useState } from 'react'
import { X, ArrowRight } from 'lucide-react'

const DISMISS_KEY = 'levy_domain_banner_v1'
const OFFICIAL_HOST = 'levylegal.ai'

/**
 * Slim announcement bar pointing existing users to the new official domain.
 *
 * Shows only when:
 *   - we're past hydration (no SSR/client mismatch),
 *   - the user hasn't dismissed it (remembered per browser via localStorage),
 *   - and we're NOT already on levylegal.ai (no point announcing the new home
 *     to someone who's already there).
 */
export function DomainBanner() {
  const [show, setShow] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const onOfficial = window.location.hostname.endsWith(OFFICIAL_HOST)
    const dismissed = window.localStorage.getItem(DISMISS_KEY) === '1'
    if (!onOfficial && !dismissed) setShow(true)
  }, [])

  if (!show) return null

  function dismiss() {
    try {
      window.localStorage.setItem(DISMISS_KEY, '1')
    } catch {
      // ignore storage failures; banner just reappears next load
    }
    setShow(false)
  }

  return (
    <div
      className="relative flex-shrink-0 flex items-center justify-center gap-2 px-9 py-1.5 text-[12px] text-emerald-50 border-b border-emerald-500/25"
      style={{
        background:
          'linear-gradient(180deg, rgba(5,150,105,0.22) 0%, rgba(5,150,105,0.12) 100%)',
      }}
    >
      <span className="text-center leading-snug">
        Levy has a new home at{' '}
        <a
          href="https://levylegal.ai"
          className="font-semibold underline decoration-emerald-300/50 underline-offset-2 hover:text-white"
        >
          levylegal.ai
        </a>
        . Update your bookmark.
        <ArrowRight className="inline-block ml-1 size-3 align-[-1px] text-emerald-300" />
      </span>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss"
        className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 rounded-md text-emerald-200/70 hover:text-white hover:bg-white/10 transition-colors"
      >
        <X className="size-3.5" />
      </button>
    </div>
  )
}
