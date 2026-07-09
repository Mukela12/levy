'use client'

/**
 * Unified premium call-to-action used for the highest-intent buttons in the
 * app: New consultation, Sign in, Upload. Three sizes (sm / md / lg) and two
 * tones (primary = emerald, ghost = neutral) keep the visual language tight.
 *
 * The look mixes: a shallow vertical gradient, a 1px inner-top highlight, an
 * outer emerald glow, and a hover sheen that fades in from the top edge.
 * Active state nudges the button down 1px for a satisfying tap.
 */

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'

type CTASize = 'sm' | 'md' | 'lg'
type CTATone = 'primary' | 'ghost'

interface CTAProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  size?: CTASize
  tone?: CTATone
  asChild?: boolean
  iconOnly?: boolean
  startIcon?: ReactNode
  children?: ReactNode
}

const SIZE_STYLES: Record<CTASize, { h: string; px: string; text: string; iconSize: string; gap: string }> = {
  sm: { h: 'h-8',  px: 'px-3',   text: 'text-[12px]',   iconSize: 'w-3.5 h-3.5', gap: 'gap-1.5' },
  md: { h: 'h-9',  px: 'px-3.5', text: 'text-[13px]',   iconSize: 'w-4 h-4',     gap: 'gap-2' },
  lg: { h: 'h-10', px: 'px-4',   text: 'text-[13.5px]', iconSize: 'w-4 h-4',     gap: 'gap-2' },
}

export const CTA = forwardRef<HTMLButtonElement, CTAProps>(function CTA(
  { size = 'md', tone = 'primary', startIcon, iconOnly = false, className = '', children, ...rest },
  ref,
) {
  const s = SIZE_STYLES[size]

  if (tone === 'ghost') {
    return (
      <button
        ref={ref}
        {...rest}
        className={`group/cta relative inline-flex items-center justify-center ${iconOnly ? 'aspect-square' : s.px} ${s.h} ${s.gap} rounded-full ${s.text} font-medium text-white/75 hover:text-white border border-white/[0.10] hover:border-white/[0.18] bg-white/[0.03] hover:bg-white/[0.06] transition-all active:translate-y-px disabled:opacity-40 disabled:cursor-not-allowed tracking-tight ${className}`}
      >
        {startIcon && <span className={s.iconSize}>{startIcon}</span>}
        {!iconOnly && children}
      </button>
    )
  }

  // Primary tone - emerald premium
  return (
    <button
      ref={ref}
      {...rest}
      className={`group/cta relative inline-flex items-center justify-center ${iconOnly ? 'aspect-square' : s.px} ${s.h} ${s.gap} rounded-full ${s.text} font-medium text-emerald-50 overflow-hidden transition-all active:translate-y-px disabled:opacity-40 disabled:cursor-not-allowed tracking-tight ${className}`}
      style={{
        background:
          'linear-gradient(180deg, rgba(20, 200, 140, 0.96) 0%, rgba(5, 150, 105, 0.96) 100%)',
        boxShadow: [
          '0 1px 0 0 rgba(255,255,255,0.22) inset',     // top inner highlight
          '0 0 0 1px rgba(5,150,105,0.55)',             // crisp edge
          '0 8px 22px -10px rgba(16,185,129,0.55)',     // emerald glow
          '0 2px 6px -2px rgba(0,0,0,0.45)',            // subtle drop
        ].join(', '),
      }}
    >
      {/* Top edge shimmer */}
      <span
        aria-hidden
        className="absolute inset-x-0 top-0 h-px"
        style={{ background: 'linear-gradient(to right, transparent, rgba(255,255,255,0.6), transparent)' }}
      />
      {/* Hover sheen */}
      <span
        aria-hidden
        className="absolute inset-0 opacity-0 group-hover/cta:opacity-100 transition-opacity duration-300"
        style={{ background: 'radial-gradient(120% 80% at 50% -10%, rgba(255,255,255,0.22) 0%, transparent 60%)' }}
      />
      {startIcon && <span className={`${s.iconSize} relative z-10`}>{startIcon}</span>}
      {!iconOnly && <span className="relative z-10">{children}</span>}
    </button>
  )
})
