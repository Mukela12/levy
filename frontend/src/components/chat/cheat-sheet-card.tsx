'use client'

/**
 * Inline "exam cheat sheet" card produced by the `make_cheat_sheet` tool in
 * Study Mode. Renders a condensed, exam-focused revision sheet (key statutes,
 * point blocks, leading cases, exam traps, a memory aid) and lets the student
 * download the same sheet as PDF or an editable Word document.
 */

import { useState } from 'react'
import { BookOpen, ChevronDown, ChevronUp, Download, Loader2, FileText, AlertTriangle, Scale, Lightbulb } from 'lucide-react'
import type { CheatSheet } from '@/lib/api'

const API_URL = process.env.NEXT_PUBLIC_API_URL || ''

export function CheatSheetCard({ sheet }: { sheet: CheatSheet }) {
  const [expanded, setExpanded] = useState(true)
  const [busy, setBusy] = useState<null | 'pdf' | 'docx'>(null)

  async function download(fmt: 'pdf' | 'docx') {
    if (busy || !sheet.artifact_id) return
    setBusy(fmt)
    try {
      const r = await fetch(`${API_URL}/api/artifacts/${sheet.artifact_id}/${fmt}`)
      if (!r.ok) throw new Error(`download ${r.status}`)
      const j = await r.json()
      const a = document.createElement('a')
      a.href = j.signed_url
      a.download = `${sheet.title}.${fmt}`
      a.target = '_blank'
      a.rel = 'noopener noreferrer'
      document.body.appendChild(a)
      a.click()
      a.remove()
    } catch {
      // best-effort
    } finally {
      setBusy(null)
    }
  }

  return (
    <div data-testid="cheat-sheet-card" className="my-3 -mx-1 rounded-xl border border-emerald-500/15 bg-emerald-500/[0.025] overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3.5 py-2.5 text-left hover:bg-emerald-500/[0.04] transition-colors"
      >
        <span className="flex items-center justify-center size-6 rounded-md bg-emerald-500/10">
          <BookOpen size={13} className="text-emerald-400" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] uppercase tracking-wider text-emerald-300/80">Cheat sheet</div>
          <div className="text-[13px] text-white/85 font-medium truncate mt-0.5">{sheet.title}</div>
        </div>
        <span className="text-white/30">{expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}</span>
      </button>

      {expanded && (
        <div className="border-t border-emerald-500/[0.08] p-3.5 space-y-3.5">
          {sheet.key_statutes && sheet.key_statutes.length > 0 && (
            <Section icon={<Scale size={12} className="text-emerald-400/70" />} title="Key statutes">
              <ul className="space-y-1">
                {sheet.key_statutes.map((s, i) => (
                  <li key={i} className="text-[12.5px] leading-snug">
                    <span className="text-emerald-300/90 font-medium">{s.name}</span>
                    {s.note ? <span className="text-white/55">: {s.note}</span> : null}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {sheet.sections.map((sec, i) => (
            <Section key={i} title={sec.heading}>
              <ul className="space-y-1 list-disc list-inside marker:text-emerald-400/40">
                {sec.points.map((p, j) => (
                  <li key={j} className="text-[12.5px] text-white/75 leading-snug">{p}</li>
                ))}
              </ul>
            </Section>
          ))}

          {sheet.key_cases && sheet.key_cases.length > 0 && (
            <Section icon={<Scale size={12} className="text-emerald-400/70" />} title="Leading cases">
              <ul className="space-y-1.5">
                {sheet.key_cases.map((c, i) => (
                  <li key={i} className="text-[12.5px] leading-snug">
                    <span className="text-white/85 font-medium italic">{c.name}</span>
                    {c.holding ? <span className="text-white/55">: {c.holding}</span> : null}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {sheet.exam_traps && sheet.exam_traps.length > 0 && (
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/[0.04] p-2.5">
              <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-amber-300/80 mb-1.5">
                <AlertTriangle size={12} /> Exam traps
              </div>
              <ul className="space-y-1 list-disc list-inside marker:text-amber-400/40">
                {sheet.exam_traps.map((t, i) => (
                  <li key={i} className="text-[12px] text-amber-100/70 leading-snug">{t}</li>
                ))}
              </ul>
            </div>
          )}

          {sheet.mnemonic && (
            <div className="flex items-start gap-2 text-[12px] text-white/70 bg-white/[0.03] rounded-lg p-2.5">
              <Lightbulb size={13} className="text-emerald-400/70 shrink-0 mt-0.5" />
              <span><span className="text-emerald-300/80 font-medium">Memory aid: </span>{sheet.mnemonic}</span>
            </div>
          )}

          {sheet.artifact_id && (
            <div className="flex items-center gap-3 pt-1">
              <span className="text-[11px] text-white/35">Save this sheet:</span>
              <button
                type="button"
                onClick={() => download('pdf')}
                disabled={busy !== null}
                className="flex items-center gap-1.5 text-[11px] text-white/55 hover:text-emerald-300 transition-colors disabled:opacity-50"
              >
                {busy === 'pdf' ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
                <span>PDF</span>
              </button>
              <button
                type="button"
                data-testid="cheat-word"
                onClick={() => download('docx')}
                disabled={busy !== null}
                className="flex items-center gap-1.5 text-[11px] text-white/55 hover:text-emerald-300 transition-colors disabled:opacity-50"
              >
                {busy === 'docx' ? <Loader2 className="size-3.5 animate-spin" /> : <FileText className="size-3.5" />}
                <span>Word</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Section({ title, icon, children }: { title: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-[12px] font-semibold text-white/80 mb-1">
        {icon}
        {title}
      </div>
      {children}
    </div>
  )
}
