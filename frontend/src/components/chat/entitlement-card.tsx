'use client'

/**
 * Inline card that renders the deterministic entitlement breakdown returned by
 * the `calculate_entitlements` tool. The figures are computed server-side
 * (no model arithmetic) and grounded in the Employment Code Act 2019; this
 * card just presents them with their statutory basis and clearly separates
 * what is owed from what is contested or still needs input.
 */

import { useState } from 'react'
import { Calculator, ChevronDown, ChevronUp, AlertTriangle } from 'lucide-react'
import type { EntitlementBreakdown, EntitlementLineItem } from '@/lib/api'

const REASON_LABEL: Record<string, string> = {
  resignation: 'Resignation',
  dismissal_with_notice: 'Dismissal (with notice)',
  summary_dismissal: 'Summary dismissal',
  redundancy: 'Redundancy',
  end_of_fixed_term: 'End of fixed term',
  medical_discharge: 'Medical discharge',
  death: 'Death in service',
  mutual_agreement: 'Mutual agreement',
  unfair_dismissal: 'Unfair dismissal',
}

const STATUS_STYLE: Record<string, { label: string; cls: string }> = {
  owed: { label: 'Owed', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25' },
  conditional: { label: 'Conditional', cls: 'bg-amber-500/12 text-amber-300 border-amber-500/25' },
  contested: { label: 'Contested', cls: 'bg-amber-500/12 text-amber-300 border-amber-500/25' },
  compliance: { label: 'Compliance', cls: 'bg-sky-500/12 text-sky-300 border-sky-500/25' },
  needs_input: { label: 'Needs input', cls: 'bg-white/[0.06] text-white/45 border-white/[0.10]' },
  not_applicable: { label: 'N/A', cls: 'bg-white/[0.03] text-white/30 border-white/[0.06]' },
}

function fmt(currency: string, amount?: number | null): string {
  if (amount === null || amount === undefined) return '—'
  const n = amount.toLocaleString('en-ZM', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${currency === 'ZMW' ? 'K' : currency + ' '}${n}`
}

export function EntitlementCard({ breakdown }: { breakdown: EntitlementBreakdown }) {
  const [expanded, setExpanded] = useState(true)
  const b = breakdown
  const reason = REASON_LABEL[b.termination_reason] || b.termination_reason

  return (
    <div className="my-3 -mx-1 rounded-xl border border-emerald-500/15 bg-emerald-500/[0.025] overflow-hidden">
      {/* Header */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3.5 py-2.5 text-left hover:bg-emerald-500/[0.04] transition-colors"
      >
        <span className="flex items-center justify-center size-6 rounded-md bg-emerald-500/10">
          <Calculator size={13} className="text-emerald-400" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] uppercase tracking-wider text-emerald-300/80">
            Entitlement estimate
          </div>
          <div className="text-[13px] text-white/85 font-medium truncate mt-0.5">
            {reason} · {b.years_of_service}yr · {fmt(b.currency, b.monthly_basic_pay)}/mo
          </div>
        </div>
        <span className="text-white/30">{expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}</span>
      </button>

      {expanded && (
        <div className="border-t border-emerald-500/[0.08] p-3.5 space-y-3">
          {/* Line items */}
          <div className="space-y-2">
            {b.line_items.map((li, i) => (
              <LineRow key={i} li={li} currency={b.currency} />
            ))}
          </div>

          {/* Total clearly owed */}
          <div className="flex items-center justify-between pt-2.5 border-t border-white/[0.08]">
            <span className="text-[12px] text-white/55">Total clearly owed</span>
            <span className="text-[15px] font-semibold text-emerald-300 tabular-nums">
              {fmt(b.currency, b.total_clearly_owed)}
            </span>
          </div>

          {(b.needs_input.length > 0 || b.contested.length > 0) && (
            <p className="text-[11px] text-amber-300/75 leading-snug flex gap-1.5">
              <AlertTriangle size={12} className="shrink-0 mt-0.5" />
              <span>
                {b.needs_input.length > 0 && (
                  <>Provide {b.needs_input.join(', ').toLowerCase()} to complete the estimate. </>
                )}
                {b.contested.length > 0 && (
                  <>Contested or conditional: {b.contested.join(', ')}. These depend on the contract and case law.</>
                )}
              </span>
            </p>
          )}

          {/* Assumptions */}
          {b.assumptions?.length > 0 && (
            <details className="text-[11px] text-white/40">
              <summary className="cursor-pointer hover:text-white/60">Assumptions &amp; method</summary>
              <ul className="mt-1.5 space-y-1 list-disc list-inside marker:text-white/20">
                {b.assumptions.map((a, i) => (
                  <li key={i} className="leading-snug">{a}</li>
                ))}
              </ul>
            </details>
          )}

          <p className="text-[10.5px] text-white/30 leading-snug pt-1 border-t border-white/[0.05]">
            {b.disclaimer}
          </p>
        </div>
      )}
    </div>
  )
}

function LineRow({ li, currency }: { li: EntitlementLineItem; currency: string }) {
  const style = STATUS_STYLE[li.status] || STATUS_STYLE.not_applicable
  const muted = li.status === 'not_applicable'
  return (
    <div className={`flex items-start gap-2.5 ${muted ? 'opacity-50' : ''}`}>
      <span className={`shrink-0 mt-0.5 px-1.5 py-0.5 rounded text-[9.5px] font-medium border ${style.cls}`}>
        {style.label}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[12.5px] text-white/85">{li.item}</span>
          <span className="text-[12.5px] text-white/70 tabular-nums shrink-0">
            {li.status === 'not_applicable' ? '—' : fmt(currency, li.amount)}
          </span>
        </div>
        {li.formula && (
          <div className="text-[10.5px] text-white/35 mt-0.5">{li.formula}</div>
        )}
        {li.note && (
          <div className="text-[10.5px] text-white/45 mt-0.5 leading-snug">{li.note}</div>
        )}
        <div className="text-[10px] text-emerald-400/45 mt-0.5">{li.basis}</div>
      </div>
    </div>
  )
}
