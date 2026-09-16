'use client'

/**
 * Onboarding tour for new and returning Levy users.
 *
 * One spotlight engine for every viewport:
 *   • A dimmed SVG-masked backdrop with a rounded cutout around the anchor.
 *   • A tooltip card positioned next to the anchor, measured AFTER render so
 *     long bodies can never overlap the spotlight.
 *   • Steps with no anchor (welcome / done) render as a centered card.
 *
 * Mobile / tablet (<md):
 *   The desktop sidebar isn't in the DOM. A step whose destination also sits
 *   in the Canopy bottom dock declares `dockSelector`, and while the dock is
 *   on screen the tour spotlights the dock item and keeps the drawer shut.
 *   Other steps that point at sidebar items declare `requiresMenu: true`;
 *   the tour asks the layout to open the mobile sidebar (its data-tour
 *   anchors live inside the same `sidebarContent` JSX so they become visible
 *   automatically), then spotlights as normal.
 *
 * Visibility is gated by `localStorage(STORAGE_KEY)` so it shows once per
 *   browser. Bump the key when the tour copy/steps change materially.
 */

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useCanonicalPath } from '@/lib/use-canonical-path'
import { createPortal } from 'react-dom'
import { motion } from 'framer-motion'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/components/auth/auth-provider'
import { createClient } from '@/lib/supabase'
import { ArrowRight, X } from 'lucide-react'
import { LevyLogo } from '@/components/ui/levy-logo'
import { useUiVariant } from '@/lib/ui-variant'

/**
 * Completion is tracked in TWO places so it survives the right things:
 *   • localStorage flag — browser-scoped; survives reloads and re-visits
 *     even for anonymous users, and is the only signal we have for them.
 *   • Supabase user_metadata.onboarded_at — account-scoped; survives across
 *     browsers and devices once the user is signed in.
 *
 * The check on auto-open reads BOTH (user_metadata wins for signed-in
 * users). The Done/Skip handler writes BOTH (best-effort on the metadata
 * update; localStorage is the always-on fallback).
 */
const STORAGE_KEY = 'levy_onboarding_v3'
const METADATA_FIELD = 'onboarded_at'

interface Step {
  image?: string
  /** Element selector to spotlight. If omitted (or none is currently visible)
   *  the card renders centered. */
  selector?: string
  /** Optional route to navigate to before this step runs. */
  route?: string
  title: string
  body: string
  /** Override anchor side. Default 'auto' (best fit). */
  side?: 'top' | 'right' | 'bottom' | 'left' | 'auto'
  /** Padding around the spotlight rect (px). */
  pad?: number
  /** On mobile, ensure the mobile sidebar is open for this step. */
  requiresMenu?: boolean
  /** Where the bottom dock is on screen, spotlight this instead and leave the
   *  sidebar shut. A drawer sliding over a phone to show one link looked
   *  clumsy when the same destination was already sitting in the dock. */
  dockSelector?: string
}

const STEPS: Step[] = [
  {
    title: 'Welcome to Levy',
    body:
      'A Zambian-law AI you can chat with, search the web with, and draft real documents from. Quick tour?',
  },
  {
    selector: '[data-tour="chat-input"]',
    title: 'Ask anything',
    body:
      'Type a legal question. Levy searches your corpus and the live web, then answers with citations.',
    side: 'top',
    pad: 6,
  },
  {
    selector: '[data-tour="web-search"]',
    title: 'Live web search',
    body:
      'Toggle Search on for current sources: parliament.gov.zm, ZPPA, PACRA, and more.',
    side: 'auto',
    pad: 4,
  },
  {
    selector: '[data-tour="attachments"]',
    title: 'Attach your own docs',
    body:
      'Drop in PDFs and Levy will search them in this chat alongside the curated library.',
    side: 'auto',
    pad: 4,
  },
  {
    // Matters shipped with a sidebar link and a data-tour anchor, but no tour
    // step ever used it — and not one user has created a Matter since. The
    // agent even tried twice to save a real hearing date into a case file that
    // did not exist. Nothing was wrong with the feature; nothing introduced it.
    selector: '[data-tour="nav-matters"]',
    route: '/chat',
    title: 'Keep a case together',
    body:
      'Running an actual case? A Matter holds the parties, the court, your cause number, key dates and every draft, so Levy remembers it next time instead of you re-explaining. Levy will offer to open one when it sees you are working a real matter.',
    side: 'auto',
    requiresMenu: true,
  },
  {
    selector: '[data-tour="nav-study"]',
    route: '/chat',
    title: 'Study mode',
    body:
      'Learn any Zambian law topic, generate exam cheat sheets, and test yourself with graded quizzes. Built for students and exam prep.',
    side: 'auto',
    requiresMenu: true,
  },
  {
    selector: '[data-tour="nav-templates"]',
    route: '/chat',
    title: 'Save templates',
    body:
      'Reusable skeletons like NDAs, demand letters and offer letters. Levy can pick one automatically when you ask it to draft.',
    side: 'auto',
    requiresMenu: true,
  },
  {
    selector: '[data-tour="nav-documents"]',
    title: 'Build your library',
    body:
      'Upload Acts, contracts, case files. Folders keep things tidy. Everything stays searchable in every chat.',
    side: 'auto',
    requiresMenu: true,
  },
  {
    selector: '[data-tour="new-chat"]',
    title: 'Fresh slate',
    body: 'New chat starts a clean conversation any time. Past chats live under Cases.',
    side: 'auto',
    requiresMenu: true,
  },
  {
    title: 'You are set',
    body: 'Ask Levy something to begin. You can replay this tour anytime from your profile.',
  },
]

const CANOPY_STEPS: Step[] = [
  { title: 'Make yourself at home.', body: 'A place for your questions, source documents and working notes. Take a short look around.', image: 'welcome' },
  { title: 'Start with what you know.', body: 'Ask in plain language, attach a PDF, or choose Review draft for text you want checked. You can follow each tool’s progress as Levy works.', image: 'ask-attach', selector: '[data-tour="chat-input"]', route: '/chat' },
  { title: 'Give your sources a home.', body: 'Group documents into folders. Open a file, ask about it, or keep it with the matter it belongs to.', image: 'documents', selector: '[data-tour="nav-documents"]', dockSelector: '[data-tour="dock-documents"]', requiresMenu: true },
  { title: 'Keep the work together.', body: 'Matters collect your conversations, documents and drafts. Create a matter when you want to keep a case together.', image: 'matters', selector: '[data-tour="nav-matters"]', dockSelector: '[data-tour="dock-matters"]', requiresMenu: true },
  { title: 'Check the work as you go.', body: 'Open the page behind a citation, inspect a calculation’s inputs, and review the IRAC analysis. Library matching does not guarantee correct legal advice.', image: 'verify-analyse', selector: '[data-tour="chat-input"]', route: '/chat' },
]

interface OnboardingTourProps {
  /** Force the tour to open even if previously dismissed. */
  forceOpen?: boolean
  /** Layout-controlled flag/setter for the mobile sidebar. The tour drives
   *  this on its sidebar steps. */
  mobileMenuOpen?: boolean
  setMobileMenuOpen?: (open: boolean) => void
  onClose?: () => void
}

export function OnboardingTour({
  forceOpen,
  mobileMenuOpen,
  setMobileMenuOpen,
  onClose,
}: OnboardingTourProps) {
  const { variant } = useUiVariant()
  const steps = variant === 'canopy' ? CANOPY_STEPS : STEPS
  const { user, loading } = useAuth()
  // "/" is the chat app via a rewrite. With the raw path the tour never
  // opened for new visitors on the bare domain; see useCanonicalPath.
  const pathname = useCanonicalPath()
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [step, setStep] = useState(0)
  const [mounted, setMounted] = useState(false)

  // Auto-open once per (browser AND account) after auth resolves.
  useEffect(() => {
    // Wait for route layout and its tour anchors before displaying a spotlight.
    const frame = requestAnimationFrame(() => {
    setMounted(true)
    if (loading) return
    if (forceOpen) {
      setOpen(true)
      setStep(0)
      return
    }
    if (typeof window === 'undefined') return
    let localSeen = false
    try { localSeen = !!window.localStorage.getItem(STORAGE_KEY) } catch { /* account state still works */ }

    // Signed-in: user_metadata is the source of truth so the tour follows
    // them across browsers and devices.
    if (user) {
      const accountSeen = !!user.user_metadata?.[METADATA_FIELD]
      if (accountSeen) {
        // Make sure local also reflects this — saves a redundant DB read
        // on every reload.
        try { if (!localSeen) window.localStorage.setItem(STORAGE_KEY, 'done') } catch { /* unavailable */ }
        return
      }
      // The user finished the tour in this browser (e.g. while anonymous)
      // but their account doesn't know yet. Backfill silently so the next
      // device they sign in on doesn't replay it.
      if (localSeen) {
        const supabase = createClient()
        supabase.auth
          .updateUser({ data: { [METADATA_FIELD]: new Date().toISOString() } })
          .catch(() => {})
        return
      }
      if (pathname.startsWith('/chat')) {
        setOpen(true)
        setStep(0)
      }
      return
    }

    // Anonymous: localStorage is all we have.
    if (!localSeen && pathname.startsWith('/chat')) {
      setOpen(true)
      setStep(0)
    }
    })
    return () => cancelAnimationFrame(frame)
  }, [loading, pathname, forceOpen, user])

  function finish() {
    if (typeof window !== 'undefined') {
      try { window.localStorage.setItem(STORAGE_KEY, 'done') } catch { /* account state remains available */ }
    }
    if (user) {
      // Best-effort. If it fails (network blip) we still have the local
      // flag and the user will not see the tour on this browser; the next
      // load on this browser also backfills.
      const supabase = createClient()
      supabase.auth
        .updateUser({ data: { [METADATA_FIELD]: new Date().toISOString() } })
        .catch(() => {})
    }
    setMobileMenuOpen?.(false)
    setOpen(false)
    onClose?.()
  }

  function next() {
    if (step >= steps.length - 1) return finish()
    const upcoming = steps[step + 1]
    if (upcoming?.route && pathname !== upcoming.route) router.push(upcoming.route)
    setStep((s) => s + 1)
  }

  function back() {
    setStep((s) => Math.max(0, s - 1))
  }

  if (!mounted || !open) return null
  return createPortal(
    <TourFrame
      step={step}
      total={steps.length}
      current={steps[step]}
      mobileMenuOpen={!!mobileMenuOpen}
      setMobileMenuOpen={setMobileMenuOpen}
      onNext={next}
      onBack={back}
      onSkip={finish}
    />,
    document.body,
  )
}

/* ---------- the visual frame ---------------------------------------------- */

/** The dock is display:none on wide screens and while a keyboard is up, so ask
 *  the page rather than guess from a breakpoint. */
function dockShowing(): boolean {
  const dock = document.querySelector<HTMLElement>('.cp-dock')
  return !!dock && dock.getBoundingClientRect().width > 0
}

function findVisibleAnchor(selector: string): HTMLElement | null {
  const candidates = document.querySelectorAll(selector)
  for (const el of Array.from(candidates)) {
    const r = (el as HTMLElement).getBoundingClientRect()
    if (r.width > 0 && r.height > 0) return el as HTMLElement
  }
  return null
}

function TourFrame({
  step,
  total,
  current,
  mobileMenuOpen,
  setMobileMenuOpen,
  onNext,
  onBack,
  onSkip,
}: {
  step: number
  total: number
  current: Step
  mobileMenuOpen: boolean
  setMobileMenuOpen?: (open: boolean) => void
  onNext: () => void
  onBack: () => void
  onSkip: () => void
}) {
  const [isDesktop, setIsDesktop] = useState(true)
  // Read on first render, not after it: starting false would open the drawer
  // for one frame on a phone before the dock was noticed.
  const [dockVisible, setDockVisible] = useState(dockShowing)
  const [rect, setRect] = useState<DOMRect | null>(null)
  const [vp, setVp] = useState({ w: 1280, h: 800 })
  const tooltipRef = useRef<HTMLDivElement>(null)
  const [tipSize, setTipSize] = useState({ w: 320, h: 160 })

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const frame = requestAnimationFrame(() => tooltipRef.current?.querySelector<HTMLButtonElement>('button')?.focus())
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onSkip(); return }
      if (event.key !== 'Tab') return
      const controls = Array.from(tooltipRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled)') ?? [])
      const first = controls[0], last = controls.at(-1)
      if (!first || !last) return
      if (event.shiftKey && (document.activeElement === first || !tooltipRef.current?.contains(document.activeElement))) {
        event.preventDefault(); last.focus()
      } else if (!event.shiftKey && (document.activeElement === last || !tooltipRef.current?.contains(document.activeElement))) {
        event.preventDefault(); first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      cancelAnimationFrame(frame)
      document.removeEventListener('keydown', onKey)
      if (previous?.isConnected) previous.focus()
    }
  }, [step, onSkip])

  // Viewport breakpoint + dimensions
  useLayoutEffect(() => {
    const measure = () => {
      setIsDesktop(window.innerWidth >= (current.image ? 1101 : 768))
      setVp({ w: window.innerWidth, h: window.innerHeight })
      setDockVisible(dockShowing())
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [current.image, step])

  // Where the dock is the navigation, point at it and leave the drawer shut.
  const onDock = dockVisible && !!current.dockSelector
  const selector = onDock ? current.dockSelector : current.selector

  // Make sure the mobile sidebar is in the right state BEFORE we try to find
  // anchors that live inside it. The effect re-runs every step change.
  useEffect(() => {
    if (isDesktop) return
    const shouldBeOpen = !!current.requiresMenu && !onDock
    if (shouldBeOpen !== mobileMenuOpen) setMobileMenuOpen?.(shouldBeOpen)
  }, [isDesktop, step, current.requiresMenu, onDock, mobileMenuOpen, setMobileMenuOpen])

  // Resolve the anchor rect. Poll briefly because the element may not yet
  // exist (route just changed, mobile sidebar still animating in, etc.).
  useLayoutEffect(() => {
    if (!selector) {
      const frame = requestAnimationFrame(() => setRect(null))
      return () => cancelAnimationFrame(frame)
    }
    let stopped = false
    let attempts = 0
    const tick = () => {
      if (stopped) return
      const el = findVisibleAnchor(selector)
      if (el) {
        setRect(el.getBoundingClientRect())
        return
      }
      attempts += 1
      if (attempts < 40) setTimeout(tick, 80)
      else setRect(null)
    }
    tick()
    return () => {
      stopped = true
    }
  }, [step, selector, isDesktop, vp.w, vp.h, mobileMenuOpen])

  // Measure the tooltip AFTER it renders so we can place it without
  // overlapping the spotlight. We re-measure when the step changes or the
  // viewport resizes (which can wrap text into more or fewer lines).
  useLayoutEffect(() => {
    if (!rect || !tooltipRef.current) return
    const r = tooltipRef.current.getBoundingClientRect()
    // scrollHeight leaves out the card's own border.
    const natural = tooltipRef.current.scrollHeight + tooltipRef.current.offsetHeight - tooltipRef.current.clientHeight
    if (
      Math.abs(r.width - tipSize.w) > 1 ||
      Math.abs(natural - tipSize.h) > 1
    ) {
      setTipSize({ w: r.width, h: natural })
    }
  }, [step, rect, vp.w, vp.h, tipSize.h, tipSize.w])

  /* ---- no anchor: centered card ---------------------------------------- */
  if (!selector || !rect) {
    return (
      <motion.div
        key={`card-${step}`}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.18 }}
        className="fixed inset-0 z-[100] flex items-end md:items-center justify-center bg-black/72 backdrop-blur-sm px-4 pb-[max(16px,env(safe-area-inset-bottom))]"
      >
        <motion.div
          ref={tooltipRef}
          role="dialog"
          aria-modal="true"
          aria-label={current.title}
          initial={{ y: 24, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 360, damping: 32 }}
          className="cp-tour-card w-full max-w-sm rounded-2xl border border-white/[0.08] bg-[#0d0d0f] p-5 shadow-[0_32px_64px_-16px_rgba(0,0,0,0.6)]"
        >
          <TourHeader step={step} total={total} onSkip={onSkip} />
          <div className="cp-tour-body">
            {current.image && <TourArt name={current.image} />}
            <h2 className="text-[17px] font-semibold text-white tracking-tight mt-2">
              {current.title}
            </h2>
            <p className="text-[13px] text-white/55 leading-relaxed mt-1.5">{current.body}</p>
          </div>
          <TourFooter step={step} total={total} onBack={onBack} onNext={onNext} />
        </motion.div>
      </motion.div>
    )
  }

  /* ---- spotlight (every viewport) -------------------------------------- */
  const pad = current.pad ?? (isDesktop ? 10 : 6)
  const spotX = Math.max(2, rect.left - pad)
  const spotY = Math.max(2, rect.top - pad)
  const spotW = Math.min(vp.w - 4, rect.width + pad * 2)
  const spotH = Math.min(vp.h - 4, rect.height + pad * 2)
  const radius = 12

  // Tooltip width adapts to viewport: smaller on small screens.
  const desiredW = isDesktop ? 320 : Math.min(320, vp.w - 32)
  const tooltipW = Math.max(240, Math.min(tipSize.w || desiredW, desiredW))
  // Use measured height when we have it; fall back to a generous estimate
  // until the first measurement lands.
  const tooltipH = Math.max(120, tipSize.h || 200)
  const gap = 12
  // The ring is drawn `pad` outside the element, so measure the gap from the
  // ring. Measured from the element, the card sat 2 to 4px off the ring.
  const reach = gap + pad

  // Pick best side automatically when unset, accounting for space available.
  const spaceTop = rect.top
  const spaceBottom = vp.h - rect.bottom
  const spaceRight = vp.w - rect.right
  const spaceLeft = rect.left
  let resolvedSide: 'top' | 'right' | 'bottom' | 'left' = 'bottom'
  if (current.side && current.side !== 'auto') {
    resolvedSide = current.side
  } else {
    // Prefer sides with the most room
    const cands: Array<['top' | 'right' | 'bottom' | 'left', number]> = [
      ['right', spaceRight - tooltipW],
      ['bottom', spaceBottom - tooltipH],
      ['top', spaceTop - tooltipH],
      ['left', spaceLeft - tooltipW],
    ]
    cands.sort((a, b) => b[1] - a[1])
    resolvedSide = cands[0][0]
  }
  // On small screens, prefer bottom/top over left/right (sidebar usually
  // occupies the full width when open).
  if (!isDesktop) {
    const fitsBelow = spaceBottom - reach - 12 >= tooltipH
    const fitsAbove = spaceTop - reach - 12 >= tooltipH
    resolvedSide = fitsBelow && !fitsAbove ? 'bottom'
      : fitsAbove && !fitsBelow ? 'top'
      : spaceBottom >= spaceTop ? 'bottom' : 'top'
  }

  let tipX = 0
  let tipY = 0
  if (resolvedSide === 'right') {
    tipX = rect.right + reach
    tipY = rect.top + rect.height / 2 - tooltipH / 2
  } else if (resolvedSide === 'left') {
    tipX = rect.left - tooltipW - reach
    tipY = rect.top + rect.height / 2 - tooltipH / 2
  } else if (resolvedSide === 'top') {
    tipX = rect.left + rect.width / 2 - tooltipW / 2
    tipY = rect.top - tooltipH - reach
  } else {
    // bottom
    tipX = rect.left + rect.width / 2 - tooltipW / 2
    tipY = rect.bottom + reach
  }
  // Clamp inside viewport with 12px margin
  tipX = Math.max(12, Math.min(tipX, vp.w - tooltipW - 12))
  tipY = Math.max(12, Math.min(tipY, vp.h - tooltipH - 12))

  // Small screens: that clamp used to slide a tall card straight over the
  // row it was pointing at. Sit beside the target instead, and if the side is
  // still too short, the card scrolls inside rather than covering it.
  let cardW = tooltipW
  let maxH: number | undefined
  if (!isDesktop) {
    cardW = vp.w - 24
    tipX = 12
    if (resolvedSide === 'bottom') {
      tipY = rect.bottom + reach
      maxH = Math.max(160, vp.h - tipY - 12)
    } else {
      maxH = Math.max(160, rect.top - reach - 12)
      tipY = Math.max(12, rect.top - reach - Math.min(tooltipH, maxH))
    }
  }

  return (
    <motion.div
      key={`spot-${step}`}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      className="fixed inset-0 z-[100] pointer-events-none"
    >
      {/* Dim + cutout */}
      <svg
        width={vp.w}
        height={vp.h}
        className="absolute inset-0 pointer-events-auto"
        onClick={onNext}
      >
        <defs>
          <mask id="levy-tour-cutout">
            <rect x="0" y="0" width={vp.w} height={vp.h} fill="white" />
            <rect
              x={spotX}
              y={spotY}
              width={spotW}
              height={spotH}
              rx={radius}
              ry={radius}
              fill="black"
            />
          </mask>
        </defs>
        <rect
          x="0"
          y="0"
          width={vp.w}
          height={vp.h}
          fill="rgba(5,8,12,0.74)"
          mask="url(#levy-tour-cutout)"
        />
        {/* Outline ring */}
        <rect
          x={spotX}
          y={spotY}
          width={spotW}
          height={spotH}
          rx={radius}
          ry={radius}
          fill="none"
          stroke="rgba(16,185,129,0.7)"
          strokeWidth={1.5}
        />
      </svg>

      {/* Tooltip — rendered with measured size for accurate placement */}
      <motion.div
        ref={tooltipRef}
        role="dialog"
        aria-modal="true"
        aria-label={current.title}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.18 }}
        className="cp-tour-card absolute pointer-events-auto rounded-2xl border border-white/[0.08] bg-[#0d0d0f] shadow-[0_28px_60px_-12px_rgba(0,0,0,0.7)] p-4"
        style={{ left: tipX, top: tipY, width: cardW, maxHeight: maxH }}
      >
        <TourHeader step={step} total={total} onSkip={onSkip} />
        {/* Only this middle scrolls on a short screen; Skip and Next stay put. */}
        <div className="cp-tour-body">
          {current.image && <TourArt name={current.image} compact={!isDesktop} />}
          <h2 className="text-[15px] font-semibold text-white tracking-tight mt-1.5">
            {current.title}
          </h2>
          <p className="text-[12.5px] text-white/55 leading-relaxed mt-1">{current.body}</p>
        </div>
        <TourFooter step={step} total={total} onBack={onBack} onNext={onNext} />
      </motion.div>
    </motion.div>
  )
}

function TourArt({ name, compact = false }: { name: string; compact?: boolean }) {
  const [paused, setPaused] = useState(false)
  return <div className={'cp-tour-art' + (compact ? ' is-compact' : '')} data-paused={paused}>
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img src={`/canopy/onboarding/${name}.webp`} alt="" width={128} height={128} decoding="async" />
    <button type="button" onClick={() => setPaused((value) => !value)} aria-pressed={paused}>{paused ? 'Resume illustration' : 'Pause illustration'}</button>
  </div>
}

function TourHeader({
  step,
  total,
  onSkip,
}: {
  step: number
  total: number
  onSkip: () => void
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-1.5">
        <LevyLogo size={14} />
        <span className="text-[10.5px] uppercase tracking-[0.12em] text-white/40">
          Tour · {step + 1}/{total}
        </span>
      </div>
      <button
        type="button"
        onClick={onSkip}
        className="min-h-11 px-3 rounded-full border border-current text-white/70 hover:text-white transition-colors text-xs flex items-center gap-1"
        aria-label="Skip tour"
      >
        Skip tour <X size={13} />
      </button>
    </div>
  )
}

function TourFooter({
  step,
  total,
  onBack,
  onNext,
}: {
  step: number
  total: number
  onBack: () => void
  onNext: () => void
}) {
  const isLast = step >= total - 1
  return (
    <div className="mt-4 flex items-center justify-between gap-2">
      <button
        type="button"
        onClick={onBack}
        disabled={step === 0}
        className="text-[12px] text-white/45 hover:text-white/75 disabled:opacity-30 disabled:cursor-not-allowed transition-colors px-2 py-1 rounded"
      >
        Back
      </button>
      <button
        type="button"
        onClick={onNext}
        className="group/cta relative inline-flex items-center justify-center gap-1.5 px-3.5 h-8 rounded-full text-[12.5px] font-medium text-emerald-50 overflow-hidden tracking-tight"
        style={{
          background:
            'linear-gradient(180deg, rgba(20, 200, 140, 0.96) 0%, rgba(5, 150, 105, 0.96) 100%)',
          boxShadow:
            '0 1px 0 0 rgba(255,255,255,0.22) inset, 0 0 0 1px rgba(5,150,105,0.55), 0 6px 14px -6px rgba(16,185,129,0.55)',
        }}
      >
        <span className="relative z-10">{isLast ? 'Done' : 'Next'}</span>
        {!isLast && <ArrowRight className="size-3.5 relative z-10" />}
      </button>
    </div>
  )
}
