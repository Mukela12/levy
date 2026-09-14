'use client'

import Image from 'next/image'
import LordIcon from '@/components/ui/lord-icon'
import { CANOPY_ICON } from './icons'
import matter from '../../../public/assets/canopy-actions/matters-case.png'

/**
 * IRAC wears the four-tile quilt icon: one tile per limb of the analysis.
 * The matter art stays a static import so a missing release asset is a
 * build error, not a broken URL.
 */
export function ActionArt({ kind, size = 40 }: { kind: 'irac' | 'matter'; size?: number }) {
  if (kind === 'irac') {
    return (
      <span className="cp-lord cp-action-art" aria-hidden="true" style={{ display: 'inline-flex', flexShrink: 0 }}>
        <LordIcon name={CANOPY_ICON.quilt} size={size} />
      </span>
    )
  }
  return <Image className="cp-action-art" src={matter} alt="" width={size} height={size} sizes={`${size}px`} style={{ width: size, height: size, objectFit: 'contain', flexShrink: 0 }} />
}
