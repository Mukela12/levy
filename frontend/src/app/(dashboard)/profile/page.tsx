'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/components/auth/auth-provider'
import { createClient } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import { ChevronRight, User, Lock, LogOut, Mail, Briefcase, CreditCard, Loader2 } from 'lucide-react'

export default function ProfilePage() {
  const { user, signOut, loading: authLoading } = useAuth()
  const router = useRouter()

  // Anonymous users have no profile to view - send them to login.
  useEffect(() => {
    if (!authLoading && !user) router.replace('/auth/login')
  }, [user, authLoading, router])
  const [changingPassword, setChangingPassword] = useState(false)
  const [passwordSent, setPasswordSent] = useState(false)

  const fullName = user?.user_metadata?.full_name || user?.email?.split('@')[0] || 'User'
  const email = user?.email || ''
  const initials = fullName.split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2)

  async function handleChangePassword() {
    if (!email) return
    setChangingPassword(true)
    try {
      const supabase = createClient()
      await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/auth/reset-password`,
      })
      setPasswordSent(true)
    } catch {
      // failed silently
    } finally {
      setChangingPassword(false)
    }
  }

  async function handleSignOut() {
    await signOut()
    router.push('/auth/login')
  }

  const infoCards = [
    { icon: Mail, label: 'Email', value: email },
    { icon: User, label: 'Full Name', value: fullName },
    { icon: Briefcase, label: 'Role', value: 'Legal Counsel' },
    { icon: CreditCard, label: 'Plan', value: 'Professional' },
  ]

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
          <p className="text-sm text-white/40">Legal Professional</p>
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
