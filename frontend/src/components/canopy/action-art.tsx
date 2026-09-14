'use client'

import Image from 'next/image'
import scales from '../../../public/assets/canopy-actions/irac-scales.png'
import matter from '../../../public/assets/canopy-actions/matters-case.png'

/** Static imports make missing release assets a build error, not a broken URL. */
export function ActionArt({ kind, size = 40 }: { kind: 'irac' | 'matter'; size?: number }) {
  return <Image className="cp-action-art" src={kind === 'irac' ? scales : matter} alt="" width={size} height={size} sizes={`${size}px`} style={{ width: size, height: size, objectFit: 'contain', flexShrink: 0 }} />
}
