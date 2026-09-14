'use client'

/**
 * The one reversible boundary between the legacy presentation and Canopy.
 *
 * The variant is decided before React paints: a build-time default
 * (NEXT_PUBLIC_UI_VARIANT) that a browser can override for preview through
 * `?ui=canopy` / `?ui=legacy` (remembered in localStorage). The override lets
 * Canopy be reviewed on the production host with the flag still off for
 * everyone else. Nothing here touches authentication, queries or the stream;
 * it only decides which shell and which stylesheet scope render.
 *
 * Theme (dark / light) is Canopy's. The legacy presentation is dark only and
 * keeps the `dark` class on <html> whatever is stored.
 */

import { createContext, useCallback, useContext, useMemo, useSyncExternalStore } from 'react'

export type UiVariant = 'legacy' | 'canopy'
export type UiTheme = 'dark' | 'light'

export const UI_STORAGE_KEY = 'levy-ui'
export const THEME_STORAGE_KEY = 'levy-theme'
export const BUILD_DEFAULT_VARIANT: UiVariant =
  process.env.NEXT_PUBLIC_UI_VARIANT === 'legacy' ? 'legacy' : 'canopy'
const CHANGE_EVENT = 'levy-ui-change'

/** Inlined by the root layout so the first paint already carries the choice. */
export const uiBootScript = `(function(){var d=document.documentElement;var q=new URLSearchParams(location.search).get('ui');var v='${BUILD_DEFAULT_VARIANT}';var t='dark';try{v=localStorage.getItem('${UI_STORAGE_KEY}')||v;t=localStorage.getItem('${THEME_STORAGE_KEY}')||t}catch(e){}if(q==='canopy'||q==='legacy'){v=q;try{localStorage.setItem('${UI_STORAGE_KEY}',q)}catch(e){}}if(v!=='canopy'&&v!=='legacy'){v='${BUILD_DEFAULT_VARIANT}'}d.dataset.ui=v;d.dataset.uiTheme=t==='light'?'light':'dark';var light=v==='canopy'&&t==='light';d.classList.toggle('dark',!light);d.style.colorScheme=light?'light':'dark'})();`

interface UiVariantValue {
  variant: UiVariant
  /** True once the browser's stored choice is in effect (server render uses the build default). */
  resolved: boolean
  theme: UiTheme
  setTheme: (next: UiTheme) => void
  setVariant: (next: UiVariant) => void
}

const UiVariantContext = createContext<UiVariantValue>({
  variant: BUILD_DEFAULT_VARIANT,
  resolved: false,
  theme: 'dark',
  setTheme: () => {},
  setVariant: () => {},
})

function subscribe(cb: () => void) {
  const onStorage = (event: StorageEvent) => {
    if (event.key === THEME_STORAGE_KEY || event.key === null) {
      applyTheme(readVariant(), event.newValue === 'light' ? 'light' : 'dark')
      cb()
    }
  }
  window.addEventListener('storage', onStorage)
  window.addEventListener(CHANGE_EVENT, cb)
  return () => {
    window.removeEventListener('storage', onStorage)
    window.removeEventListener(CHANGE_EVENT, cb)
  }
}
function readVariant(): UiVariant {
  const v = document.documentElement.dataset.ui
  return v === 'canopy' ? 'canopy' : v === 'legacy' ? 'legacy' : BUILD_DEFAULT_VARIANT
}
function readTheme(): UiTheme {
  return document.documentElement.dataset.uiTheme === 'light' ? 'light' : 'dark'
}
function applyTheme(variant: UiVariant, theme: UiTheme) {
  const d = document.documentElement
  d.dataset.uiTheme = theme
  const light = variant === 'canopy' && theme === 'light'
  d.classList.toggle('dark', !light)
  d.style.colorScheme = light ? 'light' : 'dark'
}

export function UiVariantProvider({ children }: { children: React.ReactNode }) {
  // Read what the boot script decided. During hydration the server snapshot
  // (the build default) is used, then React re-renders with the browser's
  // value; no state is set inside an effect.
  const variant = useSyncExternalStore(subscribe, readVariant, () => BUILD_DEFAULT_VARIANT)
  const theme = useSyncExternalStore(subscribe, readTheme, () => 'dark' as UiTheme)
  const resolved = useSyncExternalStore(subscribe, () => true, () => false)

  const setTheme = useCallback(
    (next: UiTheme) => {
      try {
        window.localStorage.setItem(THEME_STORAGE_KEY, next)
      } catch {
        // storage unavailable; the choice lasts for this page only
      }
      applyTheme(variant, next)
      window.dispatchEvent(new Event(CHANGE_EVENT))
    },
    [variant],
  )

  // Switching variant is a navigation-boundary change: store, then reload so
  // an active stream or viewer is never torn down mid-render.
  const setVariant = useCallback((next: UiVariant) => {
    try {
      window.localStorage.setItem(UI_STORAGE_KEY, next)
    } catch {
      // ignore
    }
    const url = new URL(window.location.href)
    url.searchParams.set('ui', next)
    window.location.assign(url.href)
  }, [])

  const value = useMemo(
    () => ({ variant, resolved, theme, setTheme, setVariant }),
    [variant, resolved, theme, setTheme, setVariant],
  )
  return <UiVariantContext.Provider value={value}>{children}</UiVariantContext.Provider>
}

export function useUiVariant() {
  return useContext(UiVariantContext)
}
