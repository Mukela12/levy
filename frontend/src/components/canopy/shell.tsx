'use client'

/**
 * Canopy dashboard shell: floating glass sidebar on desktop, glass topbar,
 * premium dock plus a navigation sheet on phones and tablets. Purely
 * presentational: it sits beneath the same ChatStream / Brief / PdfViewer
 * providers as the legacy shell, so switching presentation never remounts a
 * stream, brief or viewer.
 */

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { LogOut, PanelLeft, Trash2, X } from 'lucide-react'
import { useAuth } from '@/components/auth/auth-provider'
import { useBrief } from '@/components/chat/brief-context'
import { CanopyBriefDrawer } from './brief-drawer'
import { useChatStream } from '@/components/chat/chat-stream-context'
import { usePdfViewer } from '@/components/chat/pdf-viewer-context'
import { PdfViewer } from '@/components/chat/pdf-viewer'
import { useRecentSessions, timeAgo } from '@/components/chat/use-recent-sessions'
import { useCanonicalPath } from '@/lib/use-canonical-path'
import { useAwaitingSessions } from '@/lib/session-status'
import { OnboardingTour } from '@/components/onboarding/onboarding-tour'
import { DomainBanner } from '@/components/layout/domain-banner'
import LordIcon from '@/components/ui/lord-icon'
import { useUiVariant } from '@/lib/ui-variant'
import { CANOPY_ICON } from './icons'
import { CanopyDock, type DockDestination } from './dock'
import { CanopyMenuToggle } from './menu-toggle'
import { CanopyThemeToggle } from './theme-toggle'

const WORKSPACE = [
  { href: '/chat', label: 'Conversations', icon: 'chat', tour: 'new-chat-nav', match: /^\/chat/ },
  { href: '/acts', label: 'Legislation', icon: 'book', match: /^\/acts/ },
  { href: '/documents', label: 'Documents', icon: 'folder', tour: 'nav-documents', match: /^\/documents/ },
  { href: '/templates', label: 'Templates', icon: 'document', tour: 'nav-templates', match: /^\/templates/ },
  { href: '/matters', label: 'Matters', icon: 'work', tour: 'nav-matters', match: /^\/matters/ },
  { href: '/study', label: 'Study', icon: 'school', tour: 'nav-study', match: /^\/study/ },
] as const

const SECTION_TITLES: Array<[RegExp, string]> = [
  [/^\/chat\/.+/, 'Conversation'],
  [/^\/chat/, 'Ask Levy'],
  [/^\/acts/, 'Legislation'],
  [/^\/documents/, 'Documents'],
  [/^\/templates/, 'Templates'],
  [/^\/matters\/.+/, 'Matter'],
  [/^\/matters/, 'Matters'],
  [/^\/study/, 'Study'],
  [/^\/search/, 'Source search'],
  [/^\/profile/, 'Your account'],
]

const RAIL_KEY = 'levy-canopy-rail'

function Brand() {
  return (
    <Link href="/chat" className="cp-brand" aria-label="Levy home">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/levy-logo.svg" alt="" width={28} height={28} draggable={false} />
      <span>
        levy<span className="cp-brand-dot">.</span>
      </span>
    </Link>
  )
}

export function CanopyShell({ children }: { children: React.ReactNode }) {
  const { user, signOut } = useAuth()
  // Mark the document while an on-screen keyboard is open. Focus alone is the
  // wrong signal: the composer autofocuses on load without any keyboard. The
  // visual viewport shrinks only when a keyboard actually covers the screen.
  useEffect(() => {
    const vv = window.visualViewport
    if (!vv) return
    let baseline = vv.height
    const update = () => {
      baseline = Math.max(baseline, vv.height)
      document.documentElement.toggleAttribute('data-keyboard', vv.height < baseline * 0.78)
    }
    vv.addEventListener('resize', update)
    return () => {
      vv.removeEventListener('resize', update)
      document.documentElement.removeAttribute('data-keyboard')
    }
  }, [])

  // "/" is the chat app via a rewrite; see useCanonicalPath.
  const pathname = useCanonicalPath()
  const router = useRouter()
  const brief = useBrief()
  const pdf = usePdfViewer()
  const { streamingIds } = useChatStream()
  const { theme, setTheme } = useUiVariant()
  const { sessions, remove } = useRecentSessions(user?.id, pathname)
  const awaiting = useAwaitingSessions()
  const [navOpen, setNavOpen] = useState(false)
  const [rail, setRail] = useState(false)
  const mainRef = useRef<HTMLElement>(null)
  const [replayTour, setReplayTour] = useState(false)
  useEffect(() => {
    const replay = () => setReplayTour(true)
    window.addEventListener('levy-replay-tour', replay)
    return () => window.removeEventListener('levy-replay-tour', replay)
  }, [])

  useEffect(() => {
    try {
      setRail(window.localStorage.getItem(RAIL_KEY) === '1')
    } catch {
      /* ignore */
    }
  }, [])
  const toggleRail = () => {
    setRail((r) => {
      try {
        window.localStorage.setItem(RAIL_KEY, r ? '0' : '1')
      } catch {
        /* ignore */
      }
      return !r
    })
  }

  // Close the navigation sheet and the source viewer when the route changes:
  // both are contextual to the page that opened them.
  useEffect(() => {
    setNavOpen(false)
    pdf.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname])

  // Lock body scroll behind the sheet and the mobile brief (iOS lifts the bar otherwise).
  useEffect(() => {
    const lock = navOpen
    if (!lock) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [navOpen])

  useEffect(() => {
    if (!navOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setNavOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navOpen])

  const activeChat = pathname.match(/^\/chat\/([^/]+)$/)?.[1] ?? null
  const section = SECTION_TITLES.find(([re]) => re.test(pathname))?.[1] ?? 'Levy'
  const userName = user?.user_metadata?.full_name || user?.email?.split('@')[0] || 'Counsel'
  const initial = (user?.user_metadata?.full_name || user?.email || 'L')[0].toUpperCase()

  const dockDestinations: DockDestination[] = [
    { id: 'chat', label: 'Chat', icon: 'chat', href: activeChat ? `/chat/${activeChat}` : '/chat', tour: 'dock-chat' },
    { id: 'documents', label: 'Files', icon: 'folder', href: '/documents', tour: 'dock-documents' },
    { id: 'matters', label: 'Matters', icon: 'work', href: '/matters', tour: 'dock-matters' },
  ]
  const dockActive = pathname.startsWith('/chat')
    ? 'chat'
    : pathname.startsWith('/documents')
      ? 'documents'
      : pathname.startsWith('/matters')
        ? 'matters'
        : null

  const links = (
    <nav className="cp-nav-links" aria-label="Main navigation">
      {WORKSPACE.map((item) => {
        const current = item.match.test(pathname)
        return (
          <Link
            key={item.href}
            href={item.href}
            title={item.label}
            aria-current={current ? 'page' : undefined}
            data-tour={'tour' in item ? item.tour : undefined}
            prefetch={false}
          >
            <span className="cp-lord">
              <LordIcon name={CANOPY_ICON[item.icon]} size={20} />
            </span>
            <span>{item.label}</span>
            {current && <span className="cp-nav-active" aria-hidden="true" />}
          </Link>
        )
      })}
    </nav>
  )

  const history = user ? (
    <div className="cp-nav-history">
      <div className="cp-nav-label">Recent</div>
      {sessions.length === 0 && <p>Your conversations will appear here.</p>}
      {sessions.map((s) => {
        const current = pathname === `/chat/${s.id}`
        const thinking = streamingIds.includes(s.id)
        const needsAnswer = !thinking && awaiting.includes(s.id)
        return (
          <div key={s.id} className="cp-nav-history-row" aria-current={current ? 'page' : undefined}>
            {thinking ? (
              <span className="cp-dot is-running" role="img" aria-label="Working on an answer" style={{ marginTop: 8 }} />
            ) : needsAnswer ? (
              <span className="cp-dot is-attn" role="img" aria-label="Waiting for your answer" style={{ marginTop: 7 }} />
            ) : (
              <span className="cp-dot" aria-hidden="true" />
            )}
            <Link href={`/chat/${s.id}`} prefetch={false} title={s.title || 'New chat'}>
              <span>{s.title || 'New chat'}</span>
              <small>{timeAgo(s.created_at)}</small>
            </Link>
            <button
              type="button"
              className="cp-delete"
              aria-label={`Delete chat: ${s.title || 'New chat'}`}
              onClick={() => {
                void remove(s.id)
                if (current) router.push('/chat')
              }}
            >
              <Trash2 size={13} />
            </button>
          </div>
        )
      })}
    </div>
  ) : null

  const bottom = (
    <div className="cp-nav-bottom">
      {user ? (
        <>
          <Link href="/profile" className="cp-nav-account">
            <span className="cp-avatar">{initial}</span>
            <span style={{ minWidth: 0 }}>
              <strong style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{userName}</strong>
              <small>Your workspace</small>
            </span>
            <span className="cp-account-end cp-lord">
              <LordIcon name={CANOPY_ICON.settings} size={20} />
            </span>
          </Link>
          <button type="button" className="cp-btn ghost" style={{ marginTop: 6, minHeight: 38, fontSize: 12 }} onClick={signOut}>
            <LogOut size={14} /> Sign out
          </button>
        </>
      ) : (
        <div className="cp-nav-guest">
          <p>Sign in to save chats, upload your own documents, and pick up where you left off.</p>
          <Link href="/auth/login" className="cp-btn primary">
            Sign in
          </Link>
          <Link href="/auth/signup" className="cp-btn ghost">
            Create account
          </Link>
        </div>
      )}
    </div>
  )

  const search = (
    <Link href="/search" className="cp-nav-search" prefetch={false}>
      <span className="cp-lord">
        <LordIcon name={CANOPY_ICON.search} size={19} />
      </span>
      <span>Search sources</span>
    </Link>
  )
  const newChat = (
    <Link href="/chat" className="cp-nav-new" data-tour="new-chat" prefetch={false}>
      <span className="cp-lord">
        <LordIcon name={CANOPY_ICON.plus} size={20} />
      </span>
      New conversation
    </Link>
  )

  return (
    <div className="cp-app" data-rail={rail ? 'true' : 'false'}>
      <DomainBanner />
      <a className="cp-skip" href="#cp-main">
        Skip to content
      </a>

      <aside className={'cp-nav' + (rail ? ' is-collapsed' : '')} data-tour="navigation">
        {rail ? (
          <div className="cp-rail">
            <Brand />
            <button type="button" className="cp-icon-btn" aria-label="Expand sidebar" onClick={toggleRail}>
              <PanelLeft size={19} />
            </button>
            {links}
            {user ? (
              <Link href="/profile" className="cp-icon-btn" aria-label="Your account" style={{ marginTop: 'auto' }}>
                <span className="cp-avatar" style={{ width: 30, height: 30, fontSize: 12 }}>{initial}</span>
              </Link>
            ) : (
              <Link href="/auth/login" className="cp-icon-btn" aria-label="Sign in" style={{ marginTop: 'auto' }}>
                <LordIcon name={CANOPY_ICON.signin} size={20} />
              </Link>
            )}
          </div>
        ) : (
          <>
            <div className="cp-nav-brand">
              <Brand />
              <button type="button" className="cp-icon-btn" aria-label="Collapse sidebar" onClick={toggleRail}>
                <PanelLeft size={18} />
              </button>
            </div>
            {search}
            {newChat}
            <div className="cp-nav-label">Workspace</div>
            {links}
            {history}
            {bottom}
          </>
        )}
      </aside>

      <div className="cp-body">
        <header className="cp-topbar">
          <div className="cp-topbar-left">
            <button
              type="button"
              className="cp-icon-btn cp-mobile-toggle"
              aria-label="Open navigation"
              aria-expanded={navOpen}
              data-tour-control="menu"
              onClick={() => setNavOpen(true)}
            >
              <CanopyMenuToggle open={navOpen} />
            </button>
            <span className="cp-breadcrumb">
              <strong>{section}</strong>
            </span>
          </div>
          <div className="cp-topbar-actions">
            <CanopyThemeToggle dark={theme === 'dark'} onChange={(d) => setTheme(d ? 'dark' : 'light')} />
            {!user && (
              <Link href="/auth/login" className="cp-signin">
                Sign in
              </Link>
            )}
          </div>
        </header>
        <main ref={mainRef} id="cp-main" tabIndex={-1} className={'cp-main' + (!pathname.startsWith('/chat') ? ' cp-workspace' : '')} data-chat-route={pathname.startsWith('/chat')} data-brief-open={brief.open && brief.available}>
          {children}
          <CanopyBriefDrawer key={pathname} container={mainRef} />
        </main>
      </div>

      <CanopyDock
        destinations={dockDestinations}
        activeId={dockActive}
        moreOpen={navOpen}
        onMore={() => setNavOpen(true)}
        go={(item) => {
          setNavOpen(false)
          router.push(item.href)
        }}
      />

      {navOpen && (
        <div className="cp-sheet" role="dialog" aria-modal="true" aria-label="Your workspace">
          <div className="cp-sheet-backdrop" onClick={() => setNavOpen(false)} />
          <div className="cp-sheet-panel">
            <div className="cp-sheet-head">
              <Brand />
              <button type="button" className="cp-icon-btn" aria-label="Close navigation" onClick={() => setNavOpen(false)} autoFocus>
                <X size={20} />
              </button>
            </div>
            {search}
            {newChat}
            <div className="cp-nav-label">Workspace</div>
            {links}
            {history}
            {bottom}
          </div>
        </div>
      )}

      <PdfViewer citation={pdf.active} onClose={pdf.close} />

      <OnboardingTour forceOpen={replayTour} onClose={() => setReplayTour(false)} mobileMenuOpen={navOpen} setMobileMenuOpen={setNavOpen} />

    </div>
  )
}
