'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/components/auth/auth-provider'
import { createClient } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import { useUiVariant } from '@/lib/ui-variant'
import { ChevronRight, User, Lock, LogOut, Mail, Loader2 } from 'lucide-react'
import { CanopyThemeToggle } from '@/components/canopy/theme-toggle'

export default function ProfilePage() {
  const { user, signOut, loading: authLoading } = useAuth()
  const router = useRouter()
  const { variant, theme, setTheme } = useUiVariant()
  const [nameDraft, setNameDraft] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [profileStatus, setProfileStatus] = useState('')

  // Anonymous users have no profile to view - send them to login.
  useEffect(() => {
    if (!authLoading && !user) router.replace('/auth/login')
  }, [user, authLoading, router])
  const [changingPassword, setChangingPassword] = useState(false)
  const [passwordSent, setPasswordSent] = useState(false)
  const [passwordError, setPasswordError] = useState<string | null>(null)

  const fullName = user?.user_metadata?.full_name || user?.email?.split('@')[0] || 'User'
  const email = user?.email || ''
  const initials = fullName.split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2)

  async function handleChangePassword() {
    if (!email) return
    setChangingPassword(true)
    setPasswordError(null)
    try {
      const supabase = createClient()
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/auth/reset-password`,
      })
      if (error) throw error
      setPasswordSent(true)
    } catch {
      setPasswordError('The reset email could not be sent. Please try again.')
    } finally {
      setChangingPassword(false)
    }
  }

  async function handleSignOut() {
    try { await signOut(); router.push('/auth/login') }
    catch { setPasswordError('Could not sign out. Please try again.') }
  }

  async function saveProfile(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true); setPasswordError(null); setProfileStatus('')
    try {
      const { error } = await createClient().auth.updateUser({ data: { full_name: (nameDraft ?? fullName).trim() } })
      if (error) throw error
      setProfileStatus('Your details have been saved.')
    } catch { setPasswordError('Could not save your details. Please try again.') }
    finally { setSaving(false) }
  }

  const infoCards = [
    { icon: Mail, label: 'Email', value: email },
    { icon: User, label: 'Full Name', value: fullName },
  ]

  if (authLoading || !user) return <p role="status" className="p-8">Loading your account…</p>
  if (variant === 'canopy') return <div className="cp-account">
    <header><span className="cp-eyebrow">Make yourself at home</span><h1>Your account</h1><p>Manage your details and reading preferences.</p></header>
    <div className="cp-account-banner"><span aria-hidden="true">{initials}</span><div><h2>{fullName}</h2><p>{email}</p></div></div>
    {passwordError && <p role="alert">{passwordError}</p>}
    {profileStatus && <p role="status">{profileStatus}</p>}
    <section><h2>Personal details</h2><form onSubmit={saveProfile}><label>Name<input autoComplete="name" required maxLength={100} value={nameDraft ?? fullName} onChange={e => setNameDraft(e.target.value)} /></label><label>Email<input type="email" value={email} readOnly /><small>Your account email is shown here for reference.</small></label><button type="submit" className="cp-btn primary" disabled={saving || !(nameDraft ?? fullName).trim()}>{saving ? 'Saving…' : 'Save details'}</button></form></section>
    <section><h2>Reading preferences</h2><div className="cp-preference"><div><strong>Dark appearance</strong><p>A quieter canvas for evening research.</p></div><CanopyThemeToggle dark={theme === 'dark'} onChange={dark => setTheme(dark ? 'dark' : 'light')} /></div><div className="cp-preference"><div><strong>Password and access</strong><p>{passwordSent ? 'Check your inbox for a recovery link.' : 'Send a recovery link to your account email.'}</p></div><button className="cp-btn" onClick={handleChangePassword} disabled={changingPassword || passwordSent}>{changingPassword ? 'Sending…' : passwordSent ? 'Link sent' : 'Reset password'}</button></div><div className="cp-preference"><div><strong>Workspace tour</strong><p>A short introduction to Levy’s tools.</p></div><button className="cp-btn" onClick={() => { window.dispatchEvent(new Event('levy-replay-tour')); router.push('/chat') }}>Replay tour</button></div></section>
    <button className="cp-btn" onClick={handleSignOut}><LogOut size={16} />Sign out</button>
  </div>
  return (
    <div className="flex-1 overflow-y-auto px-6 py-8" style={{ overscrollBehavior: 'none' }}>
      <div className="max-w-md mx-auto">
        {/* Back button */}
        <button
          onClick={() => router.push('/chat')}
          className="mb-6 text-[12px] flex items-center gap-1.5 text-white/30 hover:text-emerald-400 transition-colors"
        >
          <ChevronRight size={12} className="rotate-180" />
          Back to chat
        </button>

        {/* Avatar */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-20 h-20 rounded-full bg-emerald-500/15 border border-emerald-500/20 flex items-center justify-center mb-4">
            <span className="text-2xl font-bold text-emerald-400">{initials}</span>
          </div>
          <h2
            className="text-xl font-bold text-white/90"
            style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
          >
            {fullName}
          </h2>
          <p className="text-sm text-white/40">Your Levy workspace</p>
        </div>

        {/* Info cards */}
        <div className="space-y-3">
          {infoCards.map(({ icon: Icon, label, value }) => (
            <div
              key={label}
              className="p-4 rounded-xl border border-white/[0.06] bg-white/[0.02]"
            >
              <div className="flex items-center gap-2 mb-1">
                <Icon size={12} className="text-white/25" />
                <span className="text-[10px] uppercase tracking-widest text-white/25 font-semibold">
                  {label}
                </span>
              </div>
              <p className="text-[14px] text-white/80">{value}</p>
            </div>
          ))}
        </div>

        {/* Actions */}
        <div className="mt-8 space-y-3">
          {passwordError && <p role="alert" className="text-sm text-red-400">{passwordError}</p>}
          <button
            onClick={handleChangePassword}
            disabled={changingPassword || passwordSent}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl border border-white/[0.08] text-[13px] font-medium text-white/60 hover:text-white/80 hover:bg-white/[0.02] transition-colors disabled:opacity-50"
          >
            {changingPassword ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Lock size={14} />
            )}
            {passwordSent ? 'Reset link sent to your email' : 'Change Password'}
          </button>
          <button
            onClick={handleSignOut}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl border border-red-500/20 text-[13px] font-medium text-red-400 hover:bg-red-500/5 transition-colors"
          >
            <LogOut size={14} />
            Log Out
          </button>
        </div>
      </div>
    </div>
  )
}
