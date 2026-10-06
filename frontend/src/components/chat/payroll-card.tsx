'use client'

/**
 * The payroll calculator's card (backend services/payroll.py, tool
 * `calculate_payroll`). Every figure is computed server-side from the
 * Employment Code, the 2023 wage orders, the NAPSA and NHIMA Acts and ZRA's
 * bands; this card only lays them out. Breaches lead, because the users who
 * bring payslips here are usually deciding whether someone is being underpaid.
 */

import { useState } from 'react'
import { Calculator, ChevronDown, ChevronUp } from 'lucide-react'
import type { PayrollBreakdown, PayrollCheck, PayrollLine } from '@/lib/api'

function kwacha(amount?: number | null): string {
  if (amount === null || amount === undefined) return '-'
  return `K${amount.toLocaleString('en-ZM', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function rate(amount: number): string {
  const exact = Math.abs(amount - Math.round(amount * 100) / 100) < 1e-6
  return exact ? kwacha(amount) : `K${amount.toFixed(4)}`
}

const LINE_TAG: Partial<Record<PayrollLine['status'], string>> = {
  conditional: 'Conditional',
  needs_input: 'Needs facts',
  contractual: 'Contract',
}

const ORDER_SHORT: Record<string, string> = {
  general: 'General Order',
  shop_workers: 'Shop Workers Order',
  truck_driver: 'Truck driver',
  bus_driver: 'Bus driver',
  domestic: 'Domestic worker',
}

const CHECK_TAG: Record<PayrollCheck['status'], string> = {
  ok: 'OK',
  underpaid: 'Underpaid',
  over_deducted: 'Over-deducted',
  check: 'Check',
}

export function PayrollCard({ breakdown: b }: { breakdown: PayrollBreakdown }) {
  const [expanded, setExpanded] = useState(true)
  const audited = b.audit.length > 0
  const order = ORDER_SHORT[b.wage_order]
  const who = [
    b.category && order ? `Category ${b.category}, ${order}` : order ?? null,
    `${rate(b.hourly_rate)} an hour`,
  ].filter(Boolean).join(' · ')

  return (
    <section className="pay-card" aria-label={audited ? 'Payslip check' : 'Pay calculation'}>
      <button type="button" className="pay-head" onClick={() => setExpanded((v) => !v)} aria-expanded={expanded}>
        <span className="pay-icon"><Calculator size={14} /></span>
        <span className="pay-title">
          <span className="pay-kicker">{audited ? 'Payslip check' : 'Pay calculation'}</span>
          <span className="pay-who">{who}</span>
        </span>
        {b.total_underpaid > 0 && <span className="pay-short">Short {kwacha(b.total_underpaid)}</span>}
        <span className="pay-chevron">{expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}</span>
      </button>

      {expanded && (
        <div className="pay-body">
          {b.flags.length > 0 && (
            <ul className="pay-flags">
              {b.flags.map((f, i) => (
                <li key={i} className={`pay-flag is-${f.severity}`}>
                  <span>{f.message}</span>
                  {f.basis && <span className="pay-basis">{f.basis}</span>}
                </li>
              ))}
            </ul>
          )}

          {audited && (
            <div className="pay-group">
              <h4>Payslip against the law</h4>
              {b.audit.map((c, i) => (
                <div key={i} className={`pay-row is-${c.status}`}>
                  <div className="pay-row-main">
                    <span className="pay-item">{c.item}</span>
                    <span className={`pay-tag is-${c.status}`}>{CHECK_TAG[c.status]}</span>
                  </div>
                  <div className="pay-compare">
                    <span>Paid {kwacha(c.paid)}</span>
                    {c.required !== null && <span>Law {kwacha(c.required)}</span>}
                  </div>
                  {c.note && c.status !== 'ok' && <div className="pay-note">{c.note}</div>}
                </div>
              ))}
            </div>
          )}

          <div className="pay-group">
            <h4>{audited ? 'What the law requires this month' : 'Earnings'}</h4>
            {b.earnings.map((li, i) => <Line key={i} li={li} />)}
            <div className="pay-total"><span>Gross</span><span>{kwacha(b.minimum_gross)}</span></div>
          </div>

          <div className="pay-group">
            <h4>Deductions</h4>
            {b.deductions.map((li, i) => <Line key={i} li={li} />)}
            <div className="pay-total is-net"><span>Net pay</span><span>{kwacha(b.net_pay)}</span></div>
          </div>

          <details className="pay-more">
            <summary>Employer contributions</summary>
            {b.employer_costs.map((li, i) => <Line key={i} li={li} />)}
          </details>

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

function Line({ li }: { li: PayrollLine }) {
  const tag = LINE_TAG[li.status]
  return (
    <div className={`pay-line is-${li.status}`}>
      <div className="pay-row-main">
        <span className="pay-item">
          {li.item}
          {tag && <span className={`pay-tag is-${li.status}`}>{tag}</span>}
        </span>
        <span className="pay-amount">{kwacha(li.amount)}</span>
      </div>
      {li.formula && <div className="pay-formula">{li.formula}</div>}
      {li.note && <div className="pay-note">{li.note}</div>}
      <div className="pay-basis">{li.basis}</div>
    </div>
  )
}
