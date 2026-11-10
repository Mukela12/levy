import { createBrowserClient } from '@supabase/ssr'
import { createClient as createPlainClient, type SupabaseClient } from '@supabase/supabase-js'
import { IS_APP } from './routes'

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!
const SUPABASE_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

// The iOS and Android apps keep the session in the app's own storage
// (Capacitor Preferences: UserDefaults / SharedPreferences, private to the
// app) instead of cookies, which a capacitor:// page cannot rely on. They
// use the PKCE flow, and the session survives the app being closed.
const appStorage = {
  async getItem(key: string) {
    const { Preferences } = await import('@capacitor/preferences')
    return (await Preferences.get({ key })).value
  },
  async setItem(key: string, value: string) {
    const { Preferences } = await import('@capacitor/preferences')
    await Preferences.set({ key, value })
  },
  async removeItem(key: string) {
    const { Preferences } = await import('@capacitor/preferences')
    await Preferences.remove({ key })
  },
}

let appClient: SupabaseClient | null = null

export function createClient(): SupabaseClient {
  if (IS_APP) {
    // The static export renders each page once at build time, where there is
    // no app storage and nothing to refresh.
    if (typeof window === 'undefined') {
      return createPlainClient(SUPABASE_URL, SUPABASE_KEY, { auth: { persistSession: false, autoRefreshToken: false } })
    }
    appClient ??= createPlainClient(SUPABASE_URL, SUPABASE_KEY, {
      auth: {
        flowType: 'pkce',
        storage: appStorage,
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: false,
      },
    })
    return appClient
  }
  return createBrowserClient(SUPABASE_URL, SUPABASE_KEY)
}
