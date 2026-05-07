'use client'

import { useState, useEffect } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useAuth } from '@/components/auth/auth-provider'
import AppSidebar from '@/components/layout/app-sidebar'
import { SkyToggle } from '@/components/layout/sky-toggle'
import { MenuToggleIcon } from '@/components/layout/menu-toggle-icon'
import { Scale, Loader2 } from 'lucide-react'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const [isDark, setIsDark] = useState(true)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

  useEffect(() => {
    if (!loading && !user) {
      router.push('/auth/login')
    }
  }, [user, loading, router])

  // Initialize theme from document class
  useEffect(() => {
    const hasDark = document.documentElement.classList.contains('dark')
    setIsDark(hasDark)
  }, [])

  // Close mobile sidebar on route change
  useEffect(() => {
    setMobileSidebarOpen(false)
  }, [pathname])

  function toggleTheme() {
    const next = !isDark
    setIsDark(next)
    if (next) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0a0a0b]">
        <Loader2 className="w-8 h-8 text-emerald-400 animate-spin" />
      </div>
    )
  }

  if (!user) return null

  // Derive a display name for the top bar
  const activeCaseName = pathname.startsWith('/chat/') ? 'Active Consultation' : 'Levy Counsel'

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background" style={{ overscrollBehavior: 'none' }}>
      {/* ── Top Nav Bar ── */}
      <header className="h-12 border-b border-white/[0.06] px-4 flex items-center justify-between flex-shrink-0 bg-background z-30">
        {/* Left: hamburger (mobile) / case name (desktop) */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => setMobileSidebarOpen(!mobileSidebarOpen)}
            className="md:hidden p-1.5 rounded-lg hover:bg-white/[0.04] text-foreground transition-colors"
            aria-label="Toggle menu"
          >
            <MenuToggleIcon open={mobileSidebarOpen} className="w-5 h-5" />
          </button>
          <span
            className="hidden md:block text-[13px] font-medium text-foreground/60 tracking-wide"
            style={{ fontFamily: "'Playfair Display', serif" }}
          >
            {activeCaseName}
          </span>
        </div>

        {/* Center: "Levy" logo on mobile */}
        <div className="md:hidden flex items-center gap-1.5">
          <Scale className="w-4 h-4 text-emerald-500" />
          <span
            className="text-[16px] font-semibold tracking-[-0.02em] text-foreground"
            style={{ fontFamily: "'Playfair Display', serif" }}
          >
            Levy
          </span>
        </div>

        {/* Right: SkyToggle */}
        <SkyToggle isDark={isDark} onToggle={toggleTheme} />
      </header>

      {/* ── Below top bar: sidebar + main content ── */}
      <div className="flex flex-1 overflow-hidden">
        <AppSidebar
          mobileSidebarOpen={mobileSidebarOpen}
          onCloseMobile={() => setMobileSidebarOpen(false)}
          isDark={isDark}
          onToggleTheme={toggleTheme}
        />
        <main className="flex-1 flex flex-col overflow-hidden" style={{ overscrollBehavior: 'none' }}>
          {children}
        </main>
      </div>
    </div>
  )
}
