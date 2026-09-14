'use client'

import { usePathname } from 'next/navigation'

/**
 * The route the visitor is actually looking at.
 *
 * next.config.ts serves the chat app at the bare domain through a rewrite, so
 * usePathname() reports "/" while /chat is what renders. Any component that
 * branches on "is this the chat app?" must treat the two as one place, or the
 * homepage silently behaves like a different page. That bug shipped twice
 * (workspace styling on the welcome, then an onboarding tour that never
 * opened for new visitors), so the rule lives here, once.
 */
export function useCanonicalPath(): string {
  const path = usePathname()
  return path === '/' ? '/chat' : path
}
