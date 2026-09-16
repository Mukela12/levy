'use client'

import LordIcon from '@/components/ui/lord-icon'
import { CANOPY_ICON } from './icons'

/**
 * IRAC wears the four-tile quilt icon: one tile per limb of the analysis.
 * Matters used to wear a photographic briefcase render here; it sat badly in
 * a line-icon interface and said nothing a case list needs, so the Matters
 * pages now use monograms and dates instead.
 */
export function ActionArt({ kind, size = 40 }: { kind: 'irac'; size?: number }) {
  return (
    <span className="cp-lord cp-action-art" aria-hidden="true" data-kind={kind} style={{ display: 'inline-flex', flexShrink: 0 }}>
      <LordIcon name={CANOPY_ICON.quilt} size={size} />
    </span>
  )
}
