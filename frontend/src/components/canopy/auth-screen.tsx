'use client'

import { useEffect, useState } from 'react'
import { ACCOUNT_DELETED_KEY } from '@/components/account/delete-account'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { ArrowRight, Eye, EyeOff } from 'lucide-react'
import { useAuth } from '@/components/auth/auth-provider'
import { useUiVariant } from '@/lib/ui-variant'
import { createClient } from '@/lib/supabase'
import { LevyLogo } from '@/components/ui/levy-logo'
import { CanopyThemeToggle } from './theme-toggle'
import dynamic from 'next/dynamic'
import { BookArt } from '@/components/canopy/rive-auth-scene'
import { IS_APP, linkTarget, siteRoute } from '@/lib/native'

// The Rive runtime is WASM: keep it out of SSR, and mount it only when the
// art panel can actually be seen, so phones never fetch it.
const RiveAuthScene = dynamic(() => import('@/components/canopy/rive-auth-scene'), { ssr: false, loading: () => <BookArt /> })

function useWideScreen() {
  const [wide, setWide] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 801px)')
    const apply = () => setWide(mq.matches)
    apply()
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [])
  return wide
}

export function CanopyAuthScreen({ mode }: { mode: 'login' | 'signup' | 'reset' }) {
  const wide = useWideScreen()
  const [sceneField, setSceneField] = useState<'idle' | 'email' | 'password'>('idle')
  const [sceneSignal, setSceneSignal] = useState<{ kind: 'success' | 'fail'; nonce: number } | undefined>()
  const tellScene = (kind: 'success' | 'fail') => setSceneSignal((s) => ({ kind, nonce: (s?.nonce ?? 0) + 1 }))
  const { signIn, signUp } = useAuth()
  const { theme, setTheme } = useUiVariant()
  const router = useRouter()
  const [recovery, setRecovery] = useState(false)
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const signup = mode === 'signup'
  const reset = mode === 'reset'

  // After an account is deleted the app lands here; say it worked, once.
  useEffect(() => {
    try {
      if (sessionStorage.getItem(ACCOUNT_DELETED_KEY)) {
        sessionStorage.removeItem(ACCOUNT_DELETED_KEY)
        setNotice('Your account and everything in it have been deleted.')
      }
    } catch { /* storage off: no notice */ }
  }, [])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError(''); setNotice('')
    try {
      const client = createClient()
      if (recovery) {
        const result = await client.auth.resetPasswordForEmail(email.trim(), { redirectTo: linkTarget('/auth/reset-password') })
        if (result.error) throw result.error
        setNotice('If an account exists for this address, check your inbox for a recovery link.')
        tellScene('success')
      } else if (reset) {
        const { data } = await client.auth.getSession()
        if (!data.session) throw new Error('This recovery link has expired or is invalid. Request a new link from sign in.')
        const result = await client.auth.updateUser({ password })
        if (result.error) throw result.error
        setPassword(''); setNotice('Your password has been updated. You can return to your workspace.')
        tellScene('success')
      } else if (signup) {
        const result = await signUp(email.trim(), password, name.trim())
        if (result.error) throw result.error
        if (result.session?.access_token) {
          void fetch(siteRoute('/api/email/welcome'), { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${result.session.access_token}` }, body: JSON.stringify({ fullName: name.trim() }) }).catch(() => {})
          router.push('/chat')
        } else setNotice('Check your email to confirm your account before signing in.')
        tellScene('success')
      } else {
        const result = await signIn(email.trim(), password)
        if (result.error) throw result.error
        // Let the teddy celebrate for a beat before the workspace opens.
        tellScene('success')
        setSceneField('idle')
        await new Promise((r) => setTimeout(r, 900))
        router.push('/chat')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to complete this request. Please try again.')
      tellScene('fail')
    } finally { setBusy(false) }
  }

  return <main className="cp-auth">
    <header><Link href="/chat" aria-label="Levy home"><LevyLogo size={30} /><strong>levy</strong></Link><CanopyThemeToggle dark={theme === 'dark'} onChange={dark => setTheme(dark ? 'dark' : 'light')} /></header>
    <div className="cp-auth-layout">
      <aside className="cp-auth-art"><span>A little clarity goes a long way</span><h1>Your Levy<br />workspace.</h1><p>Your companion for researching, understanding and working with Zambian law.</p>{wide ? <RiveAuthScene field={sceneField} emailLen={email.length} signal={sceneSignal} /> : <BookArt />}<small>Levy · Zambia</small></aside>
      <section className="cp-auth-form" aria-labelledby="auth-title">
        <span className="cp-eyebrow">Your Levy workspace</span>
        <h2 id="auth-title">{recovery ? 'Let’s get you back in.' : reset ? 'Choose a new password.' : signup ? 'Create your workspace.' : 'Sign in to Levy.'}</h2>
        <p>{recovery ? 'Enter the email address linked to your account.' : reset ? 'Use a password you do not use elsewhere.' : signup ? 'Your questions, sources and legal work, together.' : 'Pick up your conversations and legal research.'}</p>
        {error && <p role="alert" className="cp-auth-error">{error}</p>}
        {notice && <p role="status" className="cp-auth-notice">{notice}</p>}
        {!(notice && (reset || signup)) && <form onSubmit={submit}>
          {signup && !recovery && <label>Your name<input autoComplete="name" autoCapitalize="words" enterKeyHint="next" required maxLength={100} value={name} onChange={e => setName(e.target.value)} /></label>}
          {!reset && <label>Email address<input type="email" autoComplete="email" autoCapitalize="none" autoCorrect="off" spellCheck={false} inputMode="email" enterKeyHint={recovery ? 'send' : 'next'} required value={email} onChange={e => setEmail(e.target.value)} onFocus={() => setSceneField('email')} onBlur={() => setSceneField('idle')} /></label>}
          {!recovery && <label>Password<div className="cp-password"><input type={show ? 'text' : 'password'} autoCapitalize="none" autoCorrect="off" spellCheck={false} enterKeyHint="go" autoComplete={signup || reset ? 'new-password' : 'current-password'} minLength={signup || reset ? 8 : undefined} required value={password} onChange={e => setPassword(e.target.value)} onFocus={() => setSceneField('password')} onBlur={() => setSceneField('idle')} /><button type="button" aria-label={show ? 'Hide password' : 'Show password'} onClick={() => setShow(!show)}>{show ? <EyeOff size={18} /> : <Eye size={18} />}</button></div>{(signup || reset) && <small>At least 8 characters.</small>}</label>}
          <button className="cp-btn primary" disabled={busy} type="submit">{busy ? 'Please wait…' : recovery ? 'Send recovery link' : reset ? 'Update password' : signup ? 'Create account' : 'Sign in'}<ArrowRight size={16} /></button>
        </form>}
        {mode === 'login' && <button className="cp-auth-text" type="button" onClick={() => { setRecovery(!recovery); setError(''); setNotice('') }}>{recovery ? 'Back to sign in' : 'Forgot password?'}</button>}
        {!reset && <p>{signup ? 'Already have an account?' : 'New to Levy?'} <Link href={signup ? '/auth/login' : '/auth/signup'}>{signup ? 'Sign in' : 'Create an account'}</Link></p>}
        {/* Reachable before an account exists: the privacy policy (App Store
            5.1.1(i)) and help for someone who can't get in. */}
        <p className="cp-auth-legal"><a href="/privacy">Privacy policy</a><span aria-hidden="true">·</span><a href="/support">Help and support</a></p>
        {reset && <Link href="/auth/login">Back to sign in</Link>}
        {/* The app requires an account, so it offers no guest route. */}
        {(reset || !IS_APP) && <Link className="cp-auth-text" href="/chat">{reset ? 'Open your workspace' : 'Continue exploring without an account'}<ArrowRight size={15} /></Link>}
      </section>
    </div>
  </main>
}
