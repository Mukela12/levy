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
  process.env.NEXT_PUBLIC_UI_VARIANT === 'canopy' ? 'canopy' : 'legacy'
const CHANGE_EVENT = 'levy-ui-change'

/** Inlined by the root layout so the first paint already carries the choice. */
export const uiBootScript = `(function(){try{var d=document.documentElement;var p=new URLSearchParams(location.search);var q=p.get('ui');if(q==='canopy'||q==='legacy'){localStorage.setItem('${UI_STORAGE_KEY}',q)}var v=localStorage.getItem('${UI_STORAGE_KEY}')||'${BUILD_DEFAULT_VARIANT}';if(v!=='canopy'&&v!=='legacy'){v='${BUILD_DEFAULT_VARIANT}'}d.dataset.ui=v;var t=localStorage.getItem('${THEME_STORAGE_KEY}');if(v==='canopy'&&t==='light'){d.classList.remove('dark');d.style.colorScheme='light'}else{d.classList.add('dark');d.style.colorScheme='dark'}}catch(e){}})();`

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
  window.addEventListener('storage', cb)
  window.addEventListener(CHANGE_EVENT, cb)
  return () => {
    window.removeEventListener('storage', cb)
    window.removeEventListener(CHANGE_EVENT, cb)
  }
}
function readVariant(): UiVariant {
  const v = document.documentElement.dataset.ui
  return v === 'canopy' ? 'canopy' : v === 'legacy' ? 'legacy' : BUILD_DEFAULT_VARIANT
}
function readTheme(): UiTheme {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}
function applyTheme(variant: UiVariant, theme: UiTheme) {
  const d = document.documentElement
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
    window.location.reload()
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
