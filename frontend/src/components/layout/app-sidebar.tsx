'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/components/auth/auth-provider'
import { createClient } from '@/lib/supabase'
import {
  FolderOpen,
  Files,
  MessageSquare,
  Trash2,
  ChevronDown,
  ChevronRight,
  LogOut,
} from 'lucide-react'
import { LevyLogo } from '@/components/ui/levy-logo'

interface ChatSession {
  id: string
  title: string
  created_at: string
}

interface AppSidebarProps {
  mobileSidebarOpen: boolean
  onCloseMobile: () => void
}

export default function AppSidebar({ mobileSidebarOpen, onCloseMobile }: AppSidebarProps) {
  const { user, signOut } = useAuth()
  const pathname = usePathname()
  const router = useRouter()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [casesExpanded, setCasesExpanded] = useState(true)

  useEffect(() => {
    if (user?.id) loadSessions()
    else setSessions([])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id])

  // Close mobile menu on route change
  useEffect(() => {
    onCloseMobile()
  }, [pathname])

  async function loadSessions() {
    const supabase = createClient()
    const { data } = await supabase
      .from('chat_sessions')
      .select('id, title, created_at')
      .eq('user_id', user?.id)
      .order('created_at', { ascending: false })
      .limit(20)
    if (data) setSessions(data)
  }

  async function deleteSession(id: string) {
    const supabase = createClient()
    await supabase.from('chat_messages').delete().eq('session_id', id)
    await supabase.from('chat_sessions').delete().eq('id', id)
    setSessions((prev) => prev.filter((s) => s.id !== id))
  }

  function getTimeAgo(dateStr: string): string {
    const diff = Date.now() - new Date(dateStr).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 60) return `${mins}m ago`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours}h ago`
    const days = Math.floor(hours / 24)
    return `${days}d ago`
  }

  const userInitial = (user?.user_metadata?.full_name || user?.email || 'U')[0].toUpperCase()
  const userName = user?.user_metadata?.full_name || user?.email?.split('@')[0] || 'User'

  const sidebarContent = (
    <div className="flex flex-col h-full">
      {/* Logo Section */}
      <div className="flex items-center gap-2.5 px-4 h-[56px] flex-shrink-0">
        <LevyLogo size={28} className="flex-shrink-0" />
        <Link href="/chat" className="flex items-center">
          <span
            className="text-[18px] font-semibold tracking-[-0.02em] text-foreground"
            style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
          >
            Levy
          </span>
        </Link>
      </div>

      {/* New consultation */}
      <div className="px-3 pb-3 flex-shrink-0">
        <Link
          href="/chat"
          data-tour="new-chat"
          className="group/cta relative flex items-center justify-center gap-2 w-full h-10 rounded-xl text-[13px] font-medium text-emerald-50 overflow-hidden transition-all duration-200 active:translate-y-px tracking-tight"
          style={{
            background:
              'linear-gradient(180deg, rgba(20, 200, 140, 0.96) 0%, rgba(5, 150, 105, 0.96) 100%)',
            boxShadow: [
              '0 1px 0 0 rgba(255,255,255,0.22) inset',
              '0 0 0 1px rgba(5,150,105,0.55)',
              '0 8px 22px -10px rgba(16,185,129,0.55)',
              '0 2px 6px -2px rgba(0,0,0,0.45)',
            ].join(', '),
          }}
        >
          <span
            aria-hidden
            className="absolute inset-x-0 top-0 h-px"
            style={{ background: 'linear-gradient(to right, transparent, rgba(255,255,255,0.6), transparent)' }}
          />
          <span
            aria-hidden
            className="absolute inset-0 opacity-0 group-hover/cta:opacity-100 transition-opacity duration-300"
            style={{ background: 'radial-gradient(120% 80% at 50% -10%, rgba(255,255,255,0.22) 0%, transparent 60%)' }}
          />
          <MessageSquare className="w-3.5 h-3.5 relative z-10" />
          <span className="relative z-10">New chat</span>
        </Link>
      </div>

      {/* Divider */}
      <div className="mx-3 h-px bg-white/[0.06] flex-shrink-0" />

      {/* Cases Section - hidden for anonymous users (no saved threads to show) */}
      <div className="flex-1 overflow-y-auto overscroll-contain px-2 py-2 min-h-0" style={{ overscrollBehavior: 'contain' }}>
        {user && (
        <button
          onClick={() => setCasesExpanded(!casesExpanded)}
          className="w-full flex items-center gap-1.5 px-2.5 py-1.5 text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground/50 hover:text-muted-foreground/80 transition-colors"
        >
          {casesExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          Cases
        </button>
        )}

        {user && casesExpanded && (
          <div className="space-y-px mt-1" suppressHydrationWarning>
            {sessions.map((session) => {
              const isActive = pathname === `/chat/${session.id}`
              return (
                <div
                  key={session.id}
                  className={`group flex items-start gap-2 px-2.5 py-2 rounded-xl text-[12.5px] transition-colors cursor-pointer ${
                    isActive
                      ? 'bg-emerald-500/10'
                      : 'hover:bg-white/[0.03]'
                  }`}
                >
                  {/* Status dot */}
                  <div className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${
                    isActive ? 'bg-emerald-500' : 'bg-white/20'
                  }`} />

                  <Link
                    href={`/chat/${session.id}`}
                    prefetch={false}
                    className="flex-1 min-w-0"
                  >
                    <div className={`truncate font-medium ${isActive ? 'text-foreground' : 'text-muted-foreground'}`}>
                      {session.title || 'New chat'}
                    </div>
                    <div className="text-[10px] text-muted-foreground/40 mt-0.5">
                      {getTimeAgo(session.created_at)}
                    </div>
                  </Link>

                  <button
                    onClick={(e) => {
                      e.preventDefault()
                      deleteSession(session.id)
                    }}
                    className="opacity-0 group-hover:opacity-100 p-0.5 hover:bg-destructive/10 rounded transition-all flex-shrink-0 mt-0.5"
                  >
                    <Trash2 className="w-3 h-3 text-muted-foreground" />
                  </button>
                </div>
              )
            })}
            {sessions.length === 0 && (
              <p className="px-2.5 py-4 text-[11px] text-muted-foreground/40 text-center">
                No consultations yet
              </p>
            )}
          </div>
        )}
      </div>

      {/* Divider */}
      <div className="mx-3 h-px bg-white/[0.06] flex-shrink-0" />

      {/* Library Nav Links */}
      <div className="px-2 py-2 flex-shrink-0 space-y-px">
        <Link
          href="/documents"
          data-tour="nav-documents"
          className={`flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-[13px] font-medium transition-colors ${
            pathname.startsWith('/documents')
              ? 'bg-emerald-500/10 text-emerald-500'
              : 'text-muted-foreground hover:text-foreground hover:bg-white/[0.03]'
          }`}
        >
          <FolderOpen className="w-4 h-4" />
          <span>Documents</span>
        </Link>
        <Link
          href="/templates"
          data-tour="nav-templates"
          className={`flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-[13px] font-medium transition-colors ${
            pathname.startsWith('/templates')
              ? 'bg-emerald-500/10 text-emerald-500'
              : 'text-muted-foreground hover:text-foreground hover:bg-white/[0.03]'
          }`}
        >
          <Files className="w-4 h-4" />
          <span>Templates</span>
        </Link>
      </div>

      {/* Divider */}
      <div className="mx-3 h-px bg-white/[0.06] flex-shrink-0" />

      {/* Profile / Sign-in section. ChatGPT-style: account pill when signed
          in, persuasive sign-in CTA when anonymous. */}
      <div className="px-3 py-3 flex-shrink-0">
        {user ? (
          <>
            <Link href="/profile" className="flex items-center gap-2.5 group">
              <div className="w-8 h-8 rounded-full bg-emerald-500/15 flex items-center justify-center flex-shrink-0 text-[12px] font-semibold text-emerald-500">
                {userInitial}
              </div>
              <div className="flex-1 min-w-0">
                <div
                  className="text-[13px] font-medium text-foreground/80 truncate group-hover:text-foreground transition-colors"
                  style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
                >
                  {userName}
                </div>
                <div className="text-[10px] text-muted-foreground/40">Legal Counsel</div>
              </div>
            </Link>
            <button
              onClick={signOut}
              className="mt-2 w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-[11px] text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 transition-colors"
            >
              <LogOut className="w-3 h-3" />
              Sign out
            </button>
          </>
        ) : (
          <div className="space-y-2">
            <p className="text-[10.5px] text-white/40 leading-snug px-0.5">
              Sign in to save chats, upload your own documents, and pick up where you left off.
            </p>
            <Link
              href="/auth/login"
              className="flex items-center justify-center gap-1.5 w-full py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-[12px] font-medium text-emerald-300 hover:bg-emerald-500/15 transition-colors"
            >
              Sign in
            </Link>
            <Link
              href="/auth/signup"
              className="flex items-center justify-center gap-1.5 w-full py-2 rounded-lg text-[12px] text-white/55 hover:text-white/85 transition-colors"
            >
              Create account
            </Link>
          </div>
        )}
      </div>
    </div>
  )

  return (
    <>
      {/* Desktop Sidebar */}
      <aside className="hidden md:flex flex-col h-full bg-background border-r border-white/[0.06] w-[220px] overflow-hidden flex-shrink-0">
        {sidebarContent}
      </aside>

      {/* Mobile Overlay - fade in, NOT slide */}
      {mobileSidebarOpen && (
        <div className="fixed inset-0 z-40 md:hidden" style={{ top: '48px' }}>
          {/* Backdrop with blur */}
          <div
            className="absolute inset-0 bg-background/90 backdrop-blur-md animate-in fade-in duration-300"
            onClick={onCloseMobile}
          />
          {/* Full-screen sidebar panel - curtain fade effect */}
          <aside
            className="relative z-10 flex flex-col h-full w-full bg-background animate-in fade-in duration-300"
            style={{ overscrollBehavior: 'none' }}
          >
            {sidebarContent}
          </aside>
        </div>
      )}
    </>
  )
}
