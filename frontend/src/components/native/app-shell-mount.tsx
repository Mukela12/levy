'use client'

import dynamic from 'next/dynamic'
import { IS_APP } from '@/lib/routes'

// Loaded only in the app build, so the website never downloads the
// Capacitor plugins.
const AppShell = IS_APP
  ? dynamic(() => import('./app-shell').then((m) => m.AppShell), { ssr: false })
  : null

export function AppShellMount() {
  return AppShell ? <AppShell /> : null
}
