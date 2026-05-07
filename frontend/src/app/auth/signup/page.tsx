'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/components/auth/auth-provider'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EtherealShadow } from '@/components/ui/ethereal-shadow'
import { TextShimmer } from '@/components/ui/text-shimmer'
import { Loader2, CheckCircle, Scale } from 'lucide-react'

export default function SignUpPage() {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const { signUp } = useAuth()
  const router = useRouter()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    if (password.length < 6) {
      setError('Password must be at least 6 characters')
      setLoading(false)
      return
    }
    const { error } = await signUp(email, password, fullName)
    if (error) { setError(error.message); setLoading(false) }
    else { setSuccess(true); setLoading(false) }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative overflow-hidden bg-[#060608]">
      <EtherealShadow color="rgba(22, 163, 74, 0.4)" scale={30} speed={25} />
      <div className="absolute inset-0 pointer-events-none" style={{ background: 'radial-gradient(ellipse at 50% 30%, rgba(22, 163, 74, 0.06) 0%, transparent 60%)' }} />

      <div className="w-full max-w-[420px] relative z-10">
        <div className="rounded-3xl p-8" style={{ background: 'rgba(17, 17, 19, 0.6)', backdropFilter: 'blur(40px) saturate(150%)', border: '1px solid rgba(255, 255, 255, 0.06)', boxShadow: '0 32px 64px -12px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.04)' }}>
          {success ? (
            <div className="text-center py-4">
              <div className="mx-auto w-14 h-14 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mb-5 glow-green">
                <CheckCircle className="w-7 h-7 text-emerald-400" />
              </div>
              <h1 className="text-2xl font-bold text-white mb-2">Check Your Email</h1>
              <p className="text-[14px] text-white/40 mb-6">
                We&apos;ve sent a confirmation link to <span className="text-white/70">{email}</span>
              </p>
              <Button onClick={() => router.push('/auth/login')} className="w-full h-11 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold">
                Back to Sign In
              </Button>
            </div>
          ) : (
            <>
              <div className="text-center mb-8">
                <div className="mx-auto w-12 h-12 rounded-xl bg-white/[0.04] border border-white/[0.06] flex items-center justify-center mb-5">
                  <Scale className="w-6 h-6 text-emerald-400" />
                </div>
                <h1 className="text-2xl font-bold text-white mb-1">Create Account</h1>
                <TextShimmer className="text-sm" duration={3}>
                  Join Zambia&apos;s legal intelligence platform
                </TextShimmer>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                {error && (
                  <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/15 text-red-400 text-sm">{error}</div>
                )}
                <div className="space-y-1.5">
                  <label className="text-[12px] font-medium text-white/50 uppercase tracking-wider">Full Name</label>
                  <Input type="text" placeholder="Your full name" value={fullName} onChange={(e) => setFullName(e.target.value)} required className="h-11 rounded-xl bg-white/[0.04] border-white/[0.06] text-white placeholder:text-white/20 focus:border-emerald-500/30 focus:ring-emerald-500/10" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[12px] font-medium text-white/50 uppercase tracking-wider">Email</label>
                  <Input type="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} required className="h-11 rounded-xl bg-white/[0.04] border-white/[0.06] text-white placeholder:text-white/20 focus:border-emerald-500/30 focus:ring-emerald-500/10" />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[12px] font-medium text-white/50 uppercase tracking-wider">Password</label>
                  <Input type="password" placeholder="At least 6 characters" value={password} onChange={(e) => setPassword(e.target.value)} required className="h-11 rounded-xl bg-white/[0.04] border-white/[0.06] text-white placeholder:text-white/20 focus:border-emerald-500/30 focus:ring-emerald-500/10" />
                </div>
                <Button type="submit" disabled={loading} className="w-full h-11 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition-all hover:shadow-[0_0_24px_rgba(34,197,94,0.25)] active:scale-[0.98]">
                  {loading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                  Create Account
                </Button>
              </form>

              <p className="mt-6 text-center text-[13px] text-white/30">
                Already have an account?{' '}
                <Link href="/auth/login" className="text-emerald-400/80 hover:text-emerald-400 transition-colors">Sign in</Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
