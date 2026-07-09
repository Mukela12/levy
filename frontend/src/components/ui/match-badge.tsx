'use client'

import { cn } from '@/lib/utils'

interface MatchBadgeProps {
  percentage: number
  className?: string
}

function getMatchTier(pct: number): { label: string; bg: string; text: string; ring: string; glow: string } {
  if (pct >= 85) return {
    label: 'Excellent',
    bg: 'bg-emerald-500/15',
    text: 'text-emerald-400',
    ring: 'ring-emerald-500/25',
    glow: 'shadow-[0_0_12px_rgba(34,197,94,0.2)]',
  }
  if (pct >= 70) return {
    label: 'Strong',
    bg: 'bg-emerald-500/10',
    text: 'text-emerald-400/80',
    ring: 'ring-emerald-500/15',
    glow: '',
  }
  if (pct >= 55) return {
    label: 'Moderate',
    bg: 'bg-amber-500/10',
    text: 'text-amber-400',
    ring: 'ring-amber-500/15',
    glow: '',
  }
  return {
    label: 'Partial',
    bg: 'bg-orange-500/10',
    text: 'text-orange-400',
    ring: 'ring-orange-500/15',
    glow: '',
  }
}

export function MatchBadge({ percentage, className }: MatchBadgeProps) {
  const tier = getMatchTier(percentage)

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold tracking-wide ring-1 ring-inset transition-all',
        tier.bg, tier.text, tier.ring, tier.glow,
        className
      )}
    >
      <span
        className={cn(
          'h-1.5 w-1.5 rounded-full',
          percentage >= 85 ? 'bg-emerald-400 animate-pulse' : percentage >= 70 ? 'bg-emerald-400/80' : percentage >= 55 ? 'bg-amber-400' : 'bg-orange-400'
        )}
      />
      {tier.label}
    </span>
  )
}
