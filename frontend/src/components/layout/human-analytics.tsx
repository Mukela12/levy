'use client'

import { useEffect, useState } from 'react'
import { Analytics } from '@vercel/analytics/next'
import { SpeedInsights } from '@vercel/speed-insights/next'

/**
 * Count people, not page loads.
 *
 * Bot farms open /chat in a real browser and leave. They run the analytics
 * script like anyone else, so a load counts as a visitor: on 30 October 2026
 * Vercel recorded 5,144 page views in 7 hours, against 0 guest questions and
 * 0 signups in the database. New farms arrive with new fingerprints, so
 * blocking each one never makes the numbers honest on its own.
 *
 * Nothing is loaded until the visitor touches the page. Their page view is then
 * sent for the page they are on, and later navigation is tracked as usual. A
 * person who reads without moving the mouse or touching the screen goes
 * uncounted, which is a far smaller error than the one this removes.
 */
const INPUT_EVENTS = ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart'] as const

export function HumanAnalytics() {
  const [touched, setTouched] = useState(false)

  useEffect(() => {
    if (touched) return
    const onInput = (event: Event) => {
      if (event.isTrusted) setTouched(true)   // a script's own dispatchEvent does not count
    }
    for (const type of INPUT_EVENTS) window.addEventListener(type, onInput, { passive: true })
    return () => {
      for (const type of INPUT_EVENTS) window.removeEventListener(type, onInput)
    }
  }, [touched])

  if (!touched) return null
  return (
    <>
      <Analytics />
      <SpeedInsights />
    </>
  )
}
