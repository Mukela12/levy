/**
 * Small helpers for the iOS and Android apps (the `LEVY_TARGET=app` build).
 *
 * Everything here is a no-op or a plain web value on the website, and the
 * Capacitor plugins are imported lazily, so the website's bundles never load
 * them.
 */
import { IS_APP } from './routes'

export { IS_APP }

/** The public website. The app has no server of its own. */
export const SITE_URL = 'https://www.levylegal.ai'

/**
 * Pages only the website has (they need its server). In the app, links to
 * them open in the in-app browser instead of the bundled copy.
 */
export const WEB_ONLY_PATH = /^\/(acts|answers|privacy|admin|llms\.txt|api)(\/|$)/

/**
 * Where an emailed link (password reset, sign-up confirmation) should land.
 * On the website that is this site; in the app it is the website, because a
 * link in an email cannot open the app's bundled pages.
 */
export function linkTarget(path: string): string {
  return IS_APP ? `${SITE_URL}${path}` : `${window.location.origin}${path}`
}

/** A route handler on the website, called by full URL from the app. */
export function siteRoute(path: string): string {
  return IS_APP ? `${SITE_URL}${path}` : path
}

/** A short tap of the Taptic Engine / vibration motor. Nothing on the web. */
export function haptic(kind: 'light' | 'medium' | 'success' = 'light'): void {
  if (!IS_APP) return
  void import('@capacitor/haptics').then(({ Haptics, ImpactStyle, NotificationType }) => {
    if (kind === 'success') return Haptics.notification({ type: NotificationType.Success })
    return Haptics.impact({ style: kind === 'medium' ? ImpactStyle.Medium : ImpactStyle.Light })
  }).catch(() => {})
}

/** Opens a web page in the in-app browser (Safari View / Custom Tabs). */
export function openInBrowser(url: string): void {
  void import('@capacitor/browser')
    .then(({ Browser }) => Browser.open({ url, presentationStyle: 'popover' }))
    .catch(() => { window.location.href = url })
}
