'use client'

/**
 * Inline card listing Zambian judgments returned by the `search_case_law`
 * tool. Each case is real ingested precedent the user can open in the PDF
 * viewer. Mirrors the entitlement / application-plan card pattern.
 */

import { Scale, ExternalLink } from 'lucide-react'
import type { CaseLawMatch } from '@/lib/api'

interface PrecedentCardProps {
  cases: CaseLawMatch[]
  onOpenCase?: (documentId: string, title: string) => void
}

export function PrecedentCard({ cases, onOpenCase }: PrecedentCardProps) {
  if (!cases?.length) return null
  return (
    <div className="my-3 -mx-1 rounded-xl border border-emerald-500/15 bg-emerald-500/[0.025] overflow-hidden">
      <div className="flex items-center gap-2 px-3.5 py-2.5 border-b border-emerald-500/[0.08]">
        <span className="flex items-center justify-center size-6 rounded-md bg-emerald-500/10">
          <Scale size={13} className="text-emerald-400" />
        </span>
        <div className="text-[11px] uppercase tracking-wider text-emerald-300/80">
          Precedent · {cases.length} {cases.length === 1 ? 'case' : 'cases'}
        </div>
      </div>
      <div className="divide-y divide-white/[0.05]">
        {cases.map((c) => (
          <div key={c.document_id} className="px-3.5 py-2.5">
            <div className="flex items-start justify-between gap-2">
              <button
                type="button"
                onClick={() => onOpenCase?.(c.document_id, c.case)}
                className="text-left text-[13px] font-medium text-white/90 hover:text-emerald-300 transition-colors inline-flex items-start gap-1"
              >
                <span>{c.case}</span>
                <ExternalLink size={11} className="mt-0.5 shrink-0 text-emerald-400/60" />
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-1.5 mt-1">
              {c.court && <Chip>{c.court}</Chip>}
              {c.year && <Chip>{c.year}</Chip>}
              {c.area && c.area !== 'general' && <Chip>{c.area}</Chip>}
              {c.page_count ? <span className="text-[10px] text-white/30">{c.page_count}p</span> : null}
            </div>
            {c.holding && (
              <p className="text-[11.5px] text-white/45 mt-1.5 leading-snug line-clamp-3">
                {c.holding}
              </p>
            )}
          </div>
        ))}
      </div>
      <p className="px-3.5 py-2 text-[10px] text-white/30 border-t border-white/[0.05]">
        Judgments published by the Judiciary of Zambia. Read the full text before relying on any holding.
      </p>
    </div>
  )
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="px-1.5 py-0.5 rounded text-[9.5px] font-medium bg-white/[0.05] border border-white/[0.08] text-white/55 capitalize">
      {children}
    </span>
  )
}
