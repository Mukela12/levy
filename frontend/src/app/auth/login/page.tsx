'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/components/auth/auth-provider'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EtherealShadow } from '@/components/ui/ethereal-shadow'
import { TextShimmer } from '@/components/ui/text-shimmer'
import { Loader2 } from 'lucide-react'
import { LevyLogo } from '@/components/ui/levy-logo'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { signIn } = useAuth()
  const router = useRouter()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    const { error } = await signIn(email, password)
    if (error) {
      setError(error.message)
      setLoading(false)
    } else {
      router.push('/chat')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative overflow-hidden bg-[#060608]">
      {/* Animated ethereal background */}
      <EtherealShadow color="rgba(22, 163, 74, 0.5)" scale={35} speed={30} />

      {/* Subtle radial gradient overlay */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: 'radial-gradient(ellipse at 50% 30%, rgba(22, 163, 74, 0.06) 0%, transparent 60%)',
        }}
      />

      {/* Card */}
      <div className="w-full max-w-[420px] relative z-10">
        <div
          className="rounded-3xl p-8"
          style={{
            background: 'rgba(17, 17, 19, 0.6)',
            backdropFilter: 'blur(40px) saturate(150%)',
            border: '1px solid rgba(255, 255, 255, 0.06)',
            boxShadow: '0 32px 64px -12px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.04)',
          }}
        >
          {/* Logo */}
          <div className="text-center mb-8">
            <div className="mx-auto w-12 h-12 rounded-xl bg-white/[0.04] border border-white/[0.06] flex items-center justify-center mb-5">
              <LevyLogo size={32} />
            </div>
            <h1 className="text-2xl font-bold text-white mb-1">Welcome back</h1>
            <TextShimmer className="text-sm" duration={3}>
              AI Legal Intelligence for Zambia
            </TextShimmer>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/15 text-red-400 text-sm">
                {error}
              </div>
            )}
            <div className="space-y-1.5">
              <label className="text-[12px] font-medium text-white/50 uppercase tracking-wider">Email</label>
              <Input
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="h-11 rounded-xl bg-white/[0.04] border-white/[0.06] text-white placeholder:text-white/20 focus:border-emerald-500/30 focus:ring-emerald-500/10 transition-all"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-[12px] font-medium text-white/50 uppercase tracking-wider">Password</label>
              <Input
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="h-11 rounded-xl bg-white/[0.04] border-white/[0.06] text-white placeholder:text-white/20 focus:border-emerald-500/30 focus:ring-emerald-500/10 transition-all"
              />
            </div>
            <Button
              type="submit"
              disabled={loading}
              className="w-full h-11 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold transition-all hover:shadow-[0_0_24px_rgba(34,197,94,0.25)] active:scale-[0.98]"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Sign In
            </Button>
          </form>

          <p className="mt-6 text-center text-[13px] text-white/30">
            Don&apos;t have an account?{' '}
            <Link href="/auth/signup" className="text-emerald-400/80 hover:text-emerald-400 transition-colors">
              Create account
            </Link>
          </p>
        </div>

        <p className="mt-4 text-center text-[10px] text-white/15">
          Powered by Zambian legal intelligence
        </p>
      </div>
    </div>
  )
}
