'use client'

/**
 * Inline card that renders the structured plan returned by the
 * `recommend_application` tool. The user reviews + confirms the plan;
 * later tools (draft_summons, draft_affidavit, draft_skeletal,
 * draft_order, draft_application_bundle) consume the same fields.
 */

import { useState } from 'react'
import {
  ArrowRight,
  Building2,
  Check,
  FileText,
  Gavel,
  Scale,
  ScrollText,
  Sparkles,
} from 'lucide-react'
import type { ApplicationPlan } from '@/lib/api'

interface ApplicationPlanCardProps {
  plan: ApplicationPlan
  onDraftBundle?: () => void
  onDraftIndividual?: (kind: 'summons' | 'affidavit' | 'skeletal' | 'order') => void
}

const URGENCY_LABEL: Record<string, string> = {
  ex_parte: 'Ex Parte (without notice)',
  inter_partes: 'Inter Partes (with notice)',
}

export function ApplicationPlanCard({
  plan,
  onDraftBundle,
  onDraftIndividual,
}: ApplicationPlanCardProps) {
  const [expanded, setExpanded] = useState(true)
  const docs = plan.documents_to_file.map((d) => d.toLowerCase())
  const has = (kw: string) => docs.some((d) => d.includes(kw))

  return (
    <div className="my-3 -mx-1 rounded-xl border border-emerald-500/15 bg-emerald-500/[0.025] overflow-hidden">
      {/* Header */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3.5 py-2.5 text-left hover:bg-emerald-500/[0.04] transition-colors"
      >
        <span className="flex items-center justify-center size-6 rounded-md bg-emerald-500/10">
          <Sparkles size={12} className="text-emerald-400" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-emerald-300/80">
            Application plan
            <span className="text-white/30 normal-case tracking-normal text-[10.5px]">
              · {plan.procedural_mode}
            </span>
          </div>
          <div className="text-[13.5px] text-white/85 font-medium truncate mt-0.5">
            {plan.cause_of_action}
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-emerald-500/[0.08] p-3.5 space-y-3 text-[12.5px]">
          {/* Filing meta */}
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5">
            <Row icon={<Building2 size={11} />} label="Court" value={plan.court_division} />
            <Row icon={<Scale size={11} />} label="Mode" value={plan.procedural_mode} />
            <Row
              icon={<Gavel size={11} />}
              label="Service"
              value={URGENCY_LABEL[plan.urgency] || plan.urgency}
            />
          </dl>

          {/* Reliefs prayed for */}
          <section>
            <div className="text-[10.5px] uppercase tracking-wider text-white/40 mb-1.5">
              Reliefs prayed for
            </div>
            <ol className="space-y-1 list-decimal list-inside marker:text-emerald-400/60">
              {plan.reliefs.map((r, i) => (
                <li key={i} className="text-white/80 leading-snug">
                  {r}
                </li>
              ))}
            </ol>
          </section>

          {/* Documents to file */}
          <section>
            <div className="text-[10.5px] uppercase tracking-wider text-white/40 mb-1.5">
              Documents to file
            </div>
            <ul className="flex flex-wrap gap-1.5">
              {plan.documents_to_file.map((d, i) => (
                <li
                  key={i}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-white/[0.04] border border-white/[0.06] text-[11.5px] text-white/70"
                >
                  <ScrollText size={10} className="text-emerald-400/70" />
                  {d}
                </li>
              ))}
            </ul>
          </section>

          {/* Statutes + cases (only if present) */}
          {(plan.statutory_basis?.length || plan.authorities?.length) ? (
            <section className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {!!plan.statutory_basis?.length && (
                <div>
                  <div className="text-[10.5px] uppercase tracking-wider text-white/40 mb-1.5">
                    Statutory basis
                  </div>
                  <ul className="space-y-0.5">
                    {plan.statutory_basis.map((s, i) => (
                      <li key={i} className="text-white/65 text-[11.5px] leading-snug">
                        — {s}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {!!plan.authorities?.length && (
                <div>
                  <div className="text-[10.5px] uppercase tracking-wider text-white/40 mb-1.5">
                    Authorities
                  </div>
                  <ul className="space-y-0.5">
                    {plan.authorities.map((a, i) => (
                      <li key={i} className="text-white/65 text-[11.5px] leading-snug italic">
                        {a}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          ) : null}

          {plan.notes && (
            <p className="text-[11.5px] text-amber-300/75 leading-snug">
              {plan.notes}
            </p>
          )}

          {/* Action row */}
          {(onDraftBundle || onDraftIndividual) && (
            <div className="pt-1 flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-1.5 flex-wrap">
                {has('summons') || has('motion') ? (
                  <SmallAction
                    icon={<FileText size={11} />}
                    label="Summons"
                    onClick={() => onDraftIndividual?.('summons')}
                  />
                ) : null}
                {has('affidavit') ? (
                  <SmallAction
                    icon={<FileText size={11} />}
                    label="Affidavit"
                    onClick={() => onDraftIndividual?.('affidavit')}
                  />
                ) : null}
                {has('skeletal') ? (
                  <SmallAction
                    icon={<FileText size={11} />}
                    label="Skeletal"
                    onClick={() => onDraftIndividual?.('skeletal')}
                  />
                ) : null}
                {has('order') ? (
                  <SmallAction
                    icon={<FileText size={11} />}
                    label="Order"
                    onClick={() => onDraftIndividual?.('order')}
                  />
                ) : null}
              </div>
              {onDraftBundle && (
                <button
                  type="button"
                  onClick={onDraftBundle}
                  className="group/cta inline-flex items-center gap-1.5 px-3 h-7 rounded-full text-[11.5px] font-medium text-emerald-50 overflow-hidden tracking-tight"
                  style={{
                    background:
                      'linear-gradient(180deg, rgba(20, 200, 140, 0.96) 0%, rgba(5, 150, 105, 0.96) 100%)',
                    boxShadow:
                      '0 1px 0 0 rgba(255,255,255,0.22) inset, 0 0 0 1px rgba(5,150,105,0.55), 0 5px 14px -5px rgba(16,185,129,0.55)',
                  }}
                >
                  <Check size={11} />
                  <span>Draft the full bundle</span>
                  <ArrowRight size={11} />
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Row({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode
  label: string
  value: string
}) {
  return (
    <div className="flex items-baseline gap-2 min-w-0">
      <span className="flex items-center gap-1 shrink-0 text-white/40 text-[10.5px] uppercase tracking-wider">
        <span className="text-emerald-400/70">{icon}</span>
        {label}
      </span>
      <span className="text-white/80 truncate">{value}</span>
    </div>
  )
}

function SmallAction({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 px-2 h-7 rounded-md text-[11px] text-white/65 hover:text-white/95 bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.06] hover:border-emerald-500/30 transition-colors"
    >
      {icon}
      <span>{label}</span>
    </button>
  )
}
