'use client'

/**
 * Final pay and gratuity to date (backend services/final_pay.py, tool
 * `calculate_payroll` with mode "final_pay" or "gratuity"). Every figure is
 * computed server-side from the Employment Code and ZRA's 2026 rules; this
 * card lays them out in the order a payroll officer pays them: what is due,
 * what comes off, the net, and anything left to claim.
 */

import { useState } from 'react'
import { Calculator, ChevronDown, ChevronUp } from 'lucide-react'
import type { FinalPayBreakdown, FinalPayLine, GratuityBreakdown, PayrollFlag } from '@/lib/api'
import { kwacha } from './payroll-card'

const REASON: Record<string, string> = {
  resignation: 'Resignation',
  dismissal: 'Dismissal',
  summary_dismissal: 'Summary dismissal',
  redundancy: 'Redundancy',
  end_of_contract: 'End of contract',
  medical_discharge: 'Medical discharge',
  death: 'Death in service',
  mutual_agreement: 'Mutual agreement',
}

const CONTRACT: Record<string, string> = {
  long_term: 'long-term contract',
  fixed_term: 'fixed-term contract',
  permanent: 'permanent contract',
  casual: 'casual',
  temporary: 'temporary',
  probation: 'on probation',
}

const TAG: Partial<Record<FinalPayLine['status'], string>> = {
  conditional: 'Conditional',
  contested: 'Contested',
  needs_input: 'Needs facts',
  not_applicable: 'Not due',
  check: 'Check',
}

function day(iso: string): string {
  const d = new Date(`${iso}T00:00:00`)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function FinalPayCard({ breakdown }: { breakdown: FinalPayBreakdown | GratuityBreakdown }) {
  const [expanded, setExpanded] = useState(true)
  const gratuity = breakdown.kind === 'gratuity'
  const b = breakdown

  const who = b.kind === 'gratuity'
    ? `${Math.round(b.rate * 100)}% of basic pay · ${b.period_start ? `${day(b.period_start)} to ` : ''}${day(b.as_of)}`
    : [REASON[b.termination_reason] ?? b.termination_reason, CONTRACT[b.contract_type], `last day ${day(b.termination_date)}`]
        .filter(Boolean)
        .join(' · ')
  const chip = b.kind === 'gratuity' ? `Balance ${kwacha(b.balance)}` : `Net ${kwacha(b.net_payable)}`

  return (
    <section className="pay-card" aria-label={gratuity ? 'Gratuity to date' : 'Final pay'}>
      <button type="button" className="pay-head" onClick={() => setExpanded((v) => !v)} aria-expanded={expanded}>
        <span className="pay-icon"><Calculator size={14} /></span>
        <span className="pay-title">
          <span className="pay-kicker">{gratuity ? 'Gratuity to date' : 'Final pay'}</span>
          <span className="pay-who">{who}</span>
        </span>
        <span className="pay-chip">{chip}</span>
        <span className="pay-chevron">{expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}</span>
      </button>

      {expanded && (
        <div className="pay-body">
          {/* Warnings that change what to do lead; explanations follow the figures. */}
          <Flags flags={b.flags.filter((f) => f.severity !== 'info')} />
          {b.needs_input.length > 0 && (
            <p className="pay-needs">Still needed: {b.needs_input.join('; ')}.</p>
          )}
          {b.kind === 'gratuity' ? <GratuityBody b={b} /> : <FinalPayBody b={b} />}
          <Flags flags={b.flags.filter((f) => f.severity === 'info')} />
          {b.assumptions.length > 0 && (
            <details className="pay-more">
              <summary>Method and assumptions</summary>
              <ul>{b.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
            </details>
          )}
          <p className="pay-disclaimer">{b.disclaimer}</p>
        </div>
      )}
    </section>
  )
}

function FinalPayBody({ b }: { b: FinalPayBreakdown }) {
  const due = b.lines.filter((li) => li.group === 'due' || li.group === 'info')
  const deductions = b.lines.filter((li) => li.group === 'deduction')
  const setoff = b.lines.filter((li) => li.group === 'setoff')
  const employer = b.lines.filter((li) => li.group === 'employer')
  return (
    <>
      <div className="pay-group">
        <h4>Due on leaving</h4>
        {due.map((li, i) => <Line key={i} li={li} />)}
        <div className="pay-total"><span>Total due</span><span>{kwacha(b.total_due)}</span></div>
        {b.total_conditional > 0 && (
          <div className="pay-total is-muted"><span>Conditional or contested, not counted</span><span>{kwacha(b.total_conditional)}</span></div>
        )}
      </div>

      <div className="pay-group">
        <h4>Deductions</h4>
        {deductions.map((li, i) => <Line key={i} li={li} />)}
        {setoff.map((li, i) => <Line key={`s${i}`} li={li} />)}
        <div className="pay-total is-net"><span>Net payable</span><span>{kwacha(b.net_payable)}</span></div>
        {b.total_conditional > 0 && b.net_if_conditional_paid !== b.net_payable && (
          <div className="pay-total is-muted"><span>Net if the conditional items are paid</span><span>{kwacha(b.net_if_conditional_paid)}</span></div>
        )}
        {b.balance_claimable > 0 && (
          <div className="pay-total is-muted"><span>Left for the employer to claim, not deduct</span><span>{kwacha(b.balance_claimable)}</span></div>
        )}
      </div>

      {employer.length > 0 && (
        <details className="pay-more">
          <summary>Employer contributions</summary>
          {employer.map((li, i) => <Line key={i} li={li} />)}
        </details>
      )}
    </>
  )
}

function GratuityBody({ b }: { b: GratuityBreakdown }) {
  return (
    <div className="pay-group">
      <h4>Gratuity</h4>
      {b.lines.map((li, i) => <Line key={i} li={li} />)}
      <div className="pay-total is-net"><span>Balance to pay</span><span>{kwacha(b.balance)}</span></div>
      {b.projected_at_end !== null && b.projected_at_end !== undefined && (
        <div className="pay-total is-muted"><span>{b.advanced > 0 ? 'At the end of the contract, after advances' : 'At the end of the contract'}</span><span>{kwacha(b.projected_at_end)}</span></div>
      )}
    </div>
  )
}

function Flags({ flags }: { flags: PayrollFlag[] }) {
  if (!flags.length) return null
  return (
    <ul className="pay-flags">
      {flags.map((f, i) => (
        <li key={i} className={`pay-flag is-${f.severity}`}>
          <span>{f.message}</span>
          {f.basis && <span className="pay-basis">{f.basis}</span>}
        </li>
      ))}
    </ul>
  )
}

function Line({ li }: { li: FinalPayLine }) {
  const tag = TAG[li.status]
  const negative = li.group === 'deduction' || li.group === 'setoff'
  const amount = li.amount === null || li.amount === undefined ? null : li.amount
  return (
    <div className={`pay-line is-${li.status}`}>
      <div className="pay-row-main">
        <span className="pay-item">
          {li.item}
          {tag && <span className={`pay-tag is-${li.status}`}>{tag}</span>}
        </span>
        <span className="pay-amount">{amount === null ? '-' : `${negative && amount > 0 ? '−' : ''}${kwacha(amount)}`}</span>
      </div>
      {li.formula && <div className="pay-formula">{li.formula}</div>}
      {li.note && <div className="pay-note">{li.note}</div>}
      <div className="pay-basis">{li.basis}</div>
    </div>
  )
}
