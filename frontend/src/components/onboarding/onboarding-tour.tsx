'use client'

/**
 * Onboarding tour for new and returning Levy users.
 *
 * Desktop (md+): a spotlight overlay. A full-screen dimmed backdrop with an
 *   SVG mask cuts out a rounded rectangle around the highlighted element; a
 *   tooltip card is anchored next to that rect.
 *
 * Mobile / tablet (<md, and any step with no anchor): a centered card that
 *   names the feature with a short description, since chasing tiny anchors on
 *   small screens is fiddly and the side menus aren't visible by default.
 *
 * Visibility is gated by localStorage('levy_onboarding_v1') so it shows once
 * per browser unless the user re-opens the tour from a "Take the tour" hook.
 */

import { useEffect, useLayoutEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { motion } from 'framer-motion'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/components/auth/auth-provider'
import { ArrowRight, X, Sparkles } from 'lucide-react'

const STORAGE_KEY = 'levy_onboarding_v1'

interface Step {
  /** Element selector to spotlight on desktop. If omitted (or not found) the
   *  card renders centered. */
  selector?: string
  /** Optional route to navigate to before this step runs. */
  route?: string
  title: string
  body: string
  /** Override anchor side on desktop. Default: auto. */
  side?: 'top' | 'right' | 'bottom' | 'left'
  /** Padding around the spotlight rect (px). */
  pad?: number
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
      'Type a legal question here. Levy searches your corpus and the live web, then answers with citations.',
    side: 'top',
    pad: 8,
  },
  {
    selector: '[data-tour="web-search"]',
    title: 'Live web search',
    body:
      'Toggle Search on when you want answers grounded in current government sources — parliament.gov.zm, ZPPA, PACRA, and more.',
    side: 'top',
  },
  {
    selector: '[data-tour="attachments"]',
    title: 'Attach your own docs',
    body:
      'Drop in PDFs you care about and Levy will search them right in this chat alongside the curated library.',
    side: 'top',
  },
  {
    selector: '[data-tour="nav-templates"]',
    route: '/chat',
    title: 'Save templates',
    body:
      'Reusable skeletons — offer letters, NDAs, demand letters. When you ask Levy to draft something, it can pick the right template automatically.',
    side: 'right',
  },
  {
    selector: '[data-tour="nav-documents"]',
    title: 'Build your library',
    body:
      'Upload Acts, contracts, case files. Organise them in folders. Anything you upload is searchable in every chat.',
    side: 'right',
  },
  {
    selector: '[data-tour="new-chat"]',
    title: 'Fresh slate',
    body: 'New Chat starts a clean conversation any time. Your past chats live under Cases.',
    side: 'right',
  },
  {
    title: 'You are set',
    body:
      'Ask Levy something to begin. You can replay this tour anytime from your profile.',
  },
]

interface OnboardingTourProps {
  /** Force the tour to open even if previously dismissed. */
  forceOpen?: boolean
  onClose?: () => void
}

export function OnboardingTour({ forceOpen, onClose }: OnboardingTourProps) {
  const { user, loading } = useAuth()
  const pathname = usePathname()
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [step, setStep] = useState(0)
  const [mounted, setMounted] = useState(false)

  // Decide whether to auto-open. Run after auth resolves so we don't flash
  // for users who are about to be redirected.
  useEffect(() => {
    setMounted(true)
    if (loading) return
    if (forceOpen) {
      setOpen(true)
      setStep(0)
      return
    }
    if (typeof window === 'undefined') return
    const seen = window.localStorage.getItem(STORAGE_KEY)
    if (!seen && pathname.startsWith('/chat')) {
      setOpen(true)
      setStep(0)
    }
  }, [loading, pathname, forceOpen])

  function finish() {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, 'done')
    }
    setOpen(false)
    onClose?.()
  }

  function next() {
    if (step >= STEPS.length - 1) {
      finish()
      return
    }
    const nextStep = STEPS[step + 1]
    if (nextStep?.route && pathname !== nextStep.route) {
      router.push(nextStep.route)
    }
    setStep((s) => s + 1)
  }

  function back() {
    setStep((s) => Math.max(0, s - 1))
  }

  // user reference is kept for future per-account gating; intentionally unused
  // in the current branch.
  void user

  if (!mounted || !open) return null
  return createPortal(
    <TourFrame
      step={step}
      total={STEPS.length}
      current={STEPS[step]}
      onNext={next}
      onBack={back}
      onSkip={finish}
    />,
    document.body,
  )
}

/* ---------- the visual frame ---------------------------------------------- */

function TourFrame({
  step,
  total,
  current,
  onNext,
  onBack,
  onSkip,
}: {
  step: number
  total: number
  current: Step
  onNext: () => void
  onBack: () => void
  onSkip: () => void
}) {
  const [isDesktop, setIsDesktop] = useState(false)
  const [rect, setRect] = useState<DOMRect | null>(null)
  const [vp, setVp] = useState({ w: 1280, h: 800 })

  // Track viewport breakpoint
  useLayoutEffect(() => {
    const measure = () => {
      setIsDesktop(window.innerWidth >= 768)
      setVp({ w: window.innerWidth, h: window.innerHeight })
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

  // Resolve the spotlighted rect for the current step. Re-run on every step
  // change or when the viewport size changes. Poll briefly because the
  // anchor element may not be in the DOM yet (e.g. after navigating).
  useLayoutEffect(() => {
    if (!isDesktop || !current.selector) {
      setRect(null)
      return
    }
    let stopped = false
    let attempts = 0
    const tick = () => {
      if (stopped) return
      const el = document.querySelector(current.selector!) as HTMLElement | null
      if (el) {
        const r = el.getBoundingClientRect()
        if (r.width > 0 && r.height > 0) {
          setRect(r)
          return
        }
      }
      attempts += 1
      if (attempts < 30) setTimeout(tick, 100)
      else setRect(null)
    }
    tick()
    return () => {
      stopped = true
    }
  }, [step, current.selector, isDesktop, vp.w, vp.h])

  /* ---- mobile/tablet: centered card ------------------------------------- */
  if (!isDesktop || !current.selector || !rect) {
    return (
      <motion.div
        key={`card-${step}`}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.18 }}
        className="fixed inset-0 z-[100] flex items-end md:items-center justify-center bg-black/72 backdrop-blur-sm px-4 pb-[max(16px,env(safe-area-inset-bottom))]"
      >
        <motion.div
          initial={{ y: 24, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 360, damping: 32 }}
          className="w-full max-w-md rounded-2xl border border-white/[0.08] bg-[#0d0d0f] p-5 shadow-[0_32px_64px_-16px_rgba(0,0,0,0.6)]"
        >
          <Header step={step} total={total} onSkip={onSkip} />
          <h2 className="text-[18px] font-semibold text-white tracking-tight mt-2">
            {current.title}
          </h2>
          <p className="text-[13.5px] text-white/55 leading-relaxed mt-1.5">{current.body}</p>
          <Footer step={step} total={total} onBack={onBack} onNext={onNext} />
        </motion.div>
      </motion.div>
    )
  }

  /* ---- desktop spotlight ------------------------------------------------ */
  const pad = current.pad ?? 12
  const spotX = rect.left - pad
  const spotY = rect.top - pad
  const spotW = rect.width + pad * 2
  const spotH = rect.height + pad * 2
  const radius = 12

  // Tooltip placement
  const tooltipW = 320
  const tooltipH = 160
  const gap = 14
  let tipX = rect.right + gap
  let tipY = rect.top + rect.height / 2 - tooltipH / 2
  const side = current.side ?? 'right'
  if (side === 'right') {
    tipX = rect.right + gap
    tipY = rect.top + rect.height / 2 - tooltipH / 2
  } else if (side === 'left') {
    tipX = rect.left - tooltipW - gap
    tipY = rect.top + rect.height / 2 - tooltipH / 2
  } else if (side === 'top') {
    tipX = rect.left + rect.width / 2 - tooltipW / 2
    tipY = rect.top - tooltipH - gap
  } else {
    tipX = rect.left + rect.width / 2 - tooltipW / 2
    tipY = rect.bottom + gap
  }
  // Clamp inside viewport with 16px margin
  tipX = Math.max(16, Math.min(tipX, vp.w - tooltipW - 16))
  tipY = Math.max(16, Math.min(tipY, vp.h - tooltipH - 16))

  return (
      <motion.div
        key={`spot-${step}`}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.2 }}
        className="fixed inset-0 z-[100] pointer-events-none"
      >
        {/* Mask: dim everything except the rect */}
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
            fill="rgba(5,8,12,0.72)"
            mask="url(#levy-tour-cutout)"
          />
          {/* Subtle ring around the spotlight */}
          <rect
            x={spotX}
            y={spotY}
            width={spotW}
            height={spotH}
            rx={radius}
            ry={radius}
            fill="none"
            stroke="rgba(16,185,129,0.6)"
            strokeWidth="1.5"
          />
        </svg>

        {/* Tooltip card */}
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.18 }}
          className="absolute pointer-events-auto rounded-2xl border border-white/[0.08] bg-[#0d0d0f] shadow-[0_28px_60px_-12px_rgba(0,0,0,0.7)] p-4"
          style={{ left: tipX, top: tipY, width: tooltipW }}
        >
          <Header step={step} total={total} onSkip={onSkip} />
          <h2 className="text-[15.5px] font-semibold text-white tracking-tight mt-1.5">
            {current.title}
          </h2>
          <p className="text-[12.5px] text-white/55 leading-relaxed mt-1">{current.body}</p>
          <Footer step={step} total={total} onBack={onBack} onNext={onNext} />
        </motion.div>
      </motion.div>
  )
}

function Header({ step, total, onSkip }: { step: number; total: number; onSkip: () => void }) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-1.5">
        <span className="flex items-center justify-center size-5 rounded-md bg-emerald-500/10">
          <Sparkles size={11} className="text-emerald-400" />
        </span>
        <span className="text-[10.5px] uppercase tracking-[0.12em] text-white/40">
          Tour · {step + 1}/{total}
        </span>
      </div>
      <button
        type="button"
        onClick={onSkip}
        className="p-1 rounded text-white/30 hover:text-white/70 hover:bg-white/[0.04] transition-colors"
        aria-label="Skip tour"
      >
        <X size={13} />
      </button>
    </div>
  )
}

function Footer({
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
