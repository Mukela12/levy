'use client'

import { useState } from 'react'
import { Globe } from 'lucide-react'

/**
 * Pulls a favicon from Google's s2 service (no auth, no rate limit for our
 * scale). Falls back to a Lucide Globe icon if the image errors.
 */
export function Favicon({
  domain,
  url,
  size = 14,
  className = '',
}: {
  domain?: string
  url?: string
  size?: number
  className?: string
}) {
  const [errored, setErrored] = useState(false)
  const host = domain || extractDomain(url)

  if (!host || errored) {
    return <Globe className={className} style={{ width: size, height: size }} />
  }

  return (
    <img
      src={`https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=64`}
      alt=""
      width={size}
      height={size}
      onError={() => setErrored(true)}
      className={`rounded-sm ${className}`}
      loading="lazy"
      decoding="async"
    />
  )
}

function extractDomain(url?: string): string {
  if (!url) return ''
  try {
    return new URL(url).hostname
  } catch {
    return ''
  }
}
