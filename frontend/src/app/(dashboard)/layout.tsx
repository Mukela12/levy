'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAuth } from '@/components/auth/auth-provider'
import AppSidebar from '@/components/layout/app-sidebar'
import { SkyToggle } from '@/components/layout/sky-toggle'
import { MenuToggleIcon } from '@/components/layout/menu-toggle-icon'
import { BriefProvider, useBrief } from '@/components/chat/brief-context'
import { BriefPanel } from '@/components/chat/brief-panel'
import { PdfViewerProvider, usePdfViewer } from '@/components/chat/pdf-viewer-context'
import { PdfViewer } from '@/components/chat/pdf-viewer'
import { Scale, Loader2, X } from 'lucide-react'

function DashboardLayoutInner({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const pathname = usePathname()
  const [isDark, setIsDark] = useState(true)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const brief = useBrief()
  const pdf = usePdfViewer()
  // Anonymous users can use /chat freely (ChatGPT-style). Routes that need
  // an account guard themselves (chat/[id], profile).

  // Initialize theme from document class
  useEffect(() => {
    const hasDark = document.documentElement.classList.contains('dark')
    setIsDark(hasDark)
  }, [])

  // Close mobile sidebar on route change
  useEffect(() => {
    setMobileSidebarOpen(false)
  }, [pathname])

  // Close the PDF viewer when navigating between chats — the cited document
  // is contextual to a single message, so dragging it across routes is noise.
  useEffect(() => {
    pdf.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname])

  // Lock body scroll while the mobile sidebar or brief sheet is open
  // (otherwise the chat behind scrolls and lifts the top nav on iOS).
  useEffect(() => {
    const shouldLock = mobileSidebarOpen || brief.open
    if (shouldLock) {
      const prev = document.body.style.overflow
      document.body.style.overflow = 'hidden'
      return () => {
        document.body.style.overflow = prev
      }
    }
  }, [mobileSidebarOpen, brief.open])

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
  // No `if (!user) return null` — anonymous users get the same shell.

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

        {/* Right: Brief button (chat pages w/ messages) + SkyToggle */}
        <div className="flex items-center gap-2">
          {brief.available && (
            <button
              onClick={() => brief.setOpen(true)}
              className="lg:hidden h-8 w-8 rounded-full flex items-center justify-center text-emerald-400 transition-all active:scale-95"
              style={{
                background: 'color-mix(in oklab, rgb(34 197 94) 12%, transparent)',
                border: '1px solid color-mix(in oklab, rgb(34 197 94) 22%, transparent)',
              }}
              aria-label="Open the Brief"
            >
              <Scale className="w-4 h-4" />
            </button>
          )}
          {/* ChatGPT-style: account pill when signed in, Sign-in button when
              anonymous. Sits where the avatar would normally live. */}
          {!user && (
            <Link
              href="/auth/login"
              className="h-8 px-3 inline-flex items-center rounded-full text-[12px] font-medium text-white transition-all active:scale-[0.98]"
              style={{
                background: 'linear-gradient(180deg, rgb(16 185 129) 0%, rgb(5 150 105) 100%)',
                boxShadow:
                  '0 1px 0 0 rgba(255,255,255,0.18) inset, 0 0 0 1px rgba(16,185,129,0.45), 0 4px 12px -4px rgba(16,185,129,0.45)',
              }}
            >
              Sign in
            </Link>
          )}
          <SkyToggle isDark={isDark} onToggle={toggleTheme} />
        </div>
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

      {/* PDF source viewer (right pane on desktop, fullscreen on mobile) */}
      <PdfViewer citation={pdf.active} onClose={pdf.close} />

      {/* Mobile brief bottom sheet */}
      {brief.open && (
        <div className="lg:hidden fixed inset-0 z-50 flex flex-col">
          <div
            className="flex-1 bg-black/60 backdrop-blur-sm"
            onClick={() => brief.setOpen(false)}
          />
          <div className="bg-[#0d0d0f] border-t border-white/[0.06] rounded-t-2xl max-h-[70vh] flex flex-col">
            <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.06]">
              <span
                className="text-xs font-bold tracking-[0.2em] uppercase text-emerald-400"
                style={{ fontFamily: "'Playfair Display', serif" }}
              >
                The Brief
              </span>
              <button
                onClick={() => brief.setOpen(false)}
                className="p-1.5 rounded-lg hover:bg-white/[0.04] text-white/30 hover:text-white/60 transition-colors"
                aria-label="Close the Brief"
              >
                <X size={16} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto" style={{ overscrollBehavior: 'contain' }}>
              <BriefPanel messages={brief.messages} token={brief.token} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <BriefProvider>
      <PdfViewerProvider>
        <DashboardLayoutInner>{children}</DashboardLayoutInner>
      </PdfViewerProvider>
    </BriefProvider>
  )
}
