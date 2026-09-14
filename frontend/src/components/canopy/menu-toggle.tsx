'use client'

import { Menu, X } from 'lucide-react'

/** Established icon-library artwork, not custom decorative SVG paths. */
export function CanopyMenuToggle({ open = false, size = 22 }: { open?: boolean; size?: number }) {
  const Icon = open ? X : Menu
  return <Icon size={size} strokeWidth={1.75} aria-hidden="true" />
}
