'use client'

/**
 * Study Mode launcher. Students pick a legal area, optionally narrow to a
 * topic, choose a mode (Learn / Cheat sheet / Quiz), and start. We seed the
 * chat with a grounded prompt via /chat?q=... so the whole streaming +
 * inline-card harness is reused. Everything here is free (no payment gate).
 */

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { GraduationCap, BookOpen, ScrollText, ListChecks, ArrowRight } from 'lucide-react'
import { ChoiceSelect } from '@/components/canopy/choice-select'
import Image from 'next/image'
import { useUiVariant } from '@/lib/ui-variant'

type Mode = 'learn' | 'cheat' | 'quiz'

const MODES: { key: Mode; label: string; desc: string; Icon: typeof BookOpen }[] = [
  { key: 'learn', label: 'Learn', desc: 'A grounded lesson with statute and case law', Icon: BookOpen },
  { key: 'cheat', label: 'Cheat sheet', desc: 'A condensed revision sheet to download', Icon: ScrollText },
  { key: 'quiz', label: 'Quiz', desc: 'An interactive, graded mock exam', Icon: ListChecks },
]

const AREAS = [
  'Constitutional', 'Contract', 'Employment', 'Criminal', 'Land & Property',
  'Company', 'Family', 'Tort', 'Evidence', 'Civil Procedure',
  'Criminal Procedure', 'Administrative', 'Intellectual Property', 'Tax',
  'Banking & Finance', 'Conveyancing', 'Succession', 'Legal Ethics',
]

function buildPrompt(mode: Mode, area: string, topic: string): string {
  const subject = topic.trim() ? `${topic.trim()} (${area} law)` : `${area} law`
  if (mode === 'cheat') {
    return `Make me an exam cheat sheet on ${subject} in Zambia. Ground it in the governing Act and section numbers and the leading Zambian cases, and include the common exam traps.`
  }
  if (mode === 'quiz') {
    return `Quiz me on ${subject} in Zambia. Give me a grounded multiple choice mock exam with the correct answers, explanations and citations, then grade me.`
  }
  return `Teach me ${subject} in Zambia for my exam. Ground every point in the relevant Act and section numbers, cite the leading Zambian cases, walk through how it is applied with a short worked example, and flag the common exam pitfalls.`
}

export default function StudyPage() {
  const { variant } = useUiVariant()
  const router = useRouter()
  const [mode, setMode] = useState<Mode>('learn')
  const [area, setArea] = useState<string>('')
  const [topic, setTopic] = useState('')

  function start() {
    if (!area) return
    const q = buildPrompt(mode, area, topic)
    router.push(`/chat?q=${encodeURIComponent(q)}`)
  }

  return (
    <div className="cp-study flex-1 min-h-0 overflow-y-auto w-full max-w-2xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
      <div className="flex items-center gap-3 mb-1.5">
        {variant !== 'canopy' && <span className="flex items-center justify-center size-9 rounded-xl bg-emerald-500/12 border border-emerald-500/20">
          <GraduationCap size={18} className="text-emerald-400" />
        </span>}
        <h1 className="text-[22px] font-semibold text-white/90">Study mode</h1>
      </div>
      <p className="text-[13.5px] text-white/45 mb-7 leading-relaxed">
        Explore a topic, build revision notes or test your understanding.
      </p>

      {/* Mode */}
      {variant === 'canopy' && <>
        <div className="cp-study-banner"><h2>Your next study session</h2><Image src="/canopy/onboarding/welcome.png" alt="" width={80} height={80} /></div>
        <h2 className="cp-study-section-title">How would you like to study?</h2>
      </>}
      <div className="cp-study-modes grid grid-cols-1 sm:grid-cols-3 gap-2.5 mb-7" aria-label="Study format">
        {MODES.map(({ key, label, Icon }) => {
          const active = mode === key
          return (
            <button
              key={key}
              type="button"
              onClick={() => setMode(key)}
              aria-pressed={active}
              className={`text-left rounded-xl border p-3.5 transition-colors ${
                active
                  ? 'border-emerald-500/40 bg-emerald-500/10'
                  : 'border-white/[0.08] bg-white/[0.02] hover:bg-white/[0.04]'
              }`}
            >
              <Icon size={16} className={active ? 'text-emerald-400' : 'text-white/50'} />
              <div className={`text-[13.5px] font-medium mt-2 ${active ? 'text-emerald-100' : 'text-white/80'}`}>
                {label}
              </div>
            </button>
          )
        })}
      </div>
      <p className="cp-study-description">{MODES.find(item => item.key === mode)?.desc}</p>

      {/* Area */}
      <label htmlFor="study-subject" className="block text-sm text-white/60 mb-2.5">Subject</label>
      <div className="mb-7">
        <ChoiceSelect id="study-subject" aria-label="Study subject" value={area} onChange={e => setArea(e.target.value)} className="w-full">
          <option value="" disabled>Choose a subject</option>
          {AREAS.map(a => <option key={a} value={a}>{a}</option>)}
        </ChoiceSelect>
      </div>

      {/* Topic */}
      <label htmlFor="study-topic" className="block text-sm text-white/60 mb-2.5">
        Narrow it down <span className="text-white/25 normal-case tracking-normal">(optional)</span>
      </label>
      <input
        id="study-topic"
        type="text"
        value={topic}
        onChange={(e) => setTopic(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') start() }}
        placeholder="e.g. constructive dismissal, formation of contract, bail"
        className="w-full rounded-xl bg-white/[0.03] border border-white/[0.08] px-3.5 py-2.5 text-[13.5px] text-white/85 placeholder:text-white/30 focus:outline-none focus:border-emerald-500/40 focus:bg-white/[0.04] transition-colors mb-7"
      />

      <button
        type="button"
        onClick={start}
        disabled={!area}
        className="w-full sm:w-auto flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-[13.5px] font-semibold bg-emerald-500/15 border border-emerald-500/30 text-emerald-100 hover:bg-emerald-500/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {mode === 'learn' ? 'Start lesson' : mode === 'cheat' ? 'Make cheat sheet' : 'Start quiz'}
        <ArrowRight size={15} />
      </button>
      {!area && (
        <p className="text-[11.5px] text-white/30 mt-2.5">Pick a subject above to begin.</p>
      )}
    </div>
  )
}
