'use client'

import { useEffect } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { App } from '@capacitor/app'
import { Capacitor, SystemBars, SystemBarsStyle } from '@capacitor/core'
import { SplashScreen } from '@capacitor/splash-screen'
import { useAuth } from '@/components/auth/auth-provider'
import { createClient } from '@/lib/supabase'
import { SITE_URL, WEB_ONLY_PATH, openInBrowser } from '@/lib/native'

/**
 * Native behaviour for the iOS and Android apps. Mounted only in the app build
 * (see the root layout); renders nothing.
 */
export function AppShell() {
  const { user, loading } = useAuth()
  const pathname = usePathname()
  const router = useRouter()

  // Mark the document so CSS can tell the app from the website.
  useEffect(() => {
    const d = document.documentElement
    d.dataset.app = Capacitor.getPlatform()
  }, [])

  // The splash screen stays until the first real screen is painted, so the
  // app never flashes an empty web view. A hide sent before the native splash
  // has settled can be dropped on Android, so ask again once sign-in has
  // resolved and once more after a moment; extra hides are harmless.
  useEffect(() => {
    if (loading) return
    const hide = () => { void SplashScreen.hide({ fadeOutDuration: 220 }).catch(() => {}) }
    let second = 0
    const first = requestAnimationFrame(() => { second = requestAnimationFrame(hide) })
    const later = window.setTimeout(hide, 700)
    return () => { cancelAnimationFrame(first); cancelAnimationFrame(second); window.clearTimeout(later) }
  }, [loading])

  // Status bar icons follow the theme: light icons on the dark theme.
  useEffect(() => {
    const d = document.documentElement
    const apply = () => {
      const light = d.dataset.uiTheme === 'light'
      void SystemBars.setStyle({ style: light ? SystemBarsStyle.Light : SystemBarsStyle.Dark }).catch(() => {})
    }
    apply()
    const observer = new MutationObserver(apply)
    observer.observe(d, { attributes: true, attributeFilter: ['data-ui-theme'] })
    return () => observer.disconnect()
  }, [])

  // The app needs an account: Levy's guest check is built for the website.
  useEffect(() => {
    if (loading || user) return
    if (!pathname.startsWith('/auth')) router.replace('/auth/login/')
  }, [loading, user, pathname, router])

  // Android back button: close whatever is open, then go back, and at the
  // first screen send the app to the background (it keeps its state).
  useEffect(() => {
    const listener = App.addListener('backButton', ({ canGoBack }) => {
      const dialog = document.querySelector('[role="dialog"][aria-modal="true"]')
      if (dialog) {
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
        const close = dialog.querySelector<HTMLElement>('[aria-label^="Close"]')
        close?.click()
        return
      }
      if (canGoBack && window.history.length > 1) window.history.back()
      else void App.minimizeApp()
    })
    return () => { void listener.then((l) => l.remove()) }
  }, [])

  // Sessions refresh only while the app is in front; on return, refresh at
  // once and tell open chats to reconcile anything that finished meanwhile.
  useEffect(() => {
    const auth = createClient().auth
    void auth.startAutoRefresh()
    const listener = App.addListener('appStateChange', ({ isActive }) => {
      if (isActive) {
        void auth.startAutoRefresh()
        window.dispatchEvent(new Event('levy-app-resume'))
      } else {
        void auth.stopAutoRefresh()
      }
    })
    return () => { void listener.then((l) => l.remove()) }
  }, [])

  // Links to the website (Acts, Answers, the privacy policy) and to other
  // sites open in the in-app browser instead of replacing the app.
  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return
      const anchor = (event.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null
      if (!anchor || anchor.hasAttribute('download')) return
      const url = new URL(anchor.href, window.location.href)
      if (url.protocol === 'mailto:' || url.protocol === 'tel:') return
      const local = url.origin === window.location.origin
      if (local && !WEB_ONLY_PATH.test(url.pathname)) return
      event.preventDefault()
      openInBrowser(local ? `${SITE_URL}${url.pathname}${url.search}${url.hash}` : url.href)
    }
    document.addEventListener('click', onClick, true)

    const nativeOpen = window.open
    window.open = (target?: string | URL, ...rest) => {
      const href = target ? String(target) : ''
      if (/^https?:/i.test(href)) {
        openInBrowser(href)
        return null
      }
      return nativeOpen.call(window, target, ...rest)
    }
    return () => {
      document.removeEventListener('click', onClick, true)
      window.open = nativeOpen
    }
  }, [])

  return null
}
