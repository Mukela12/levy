'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/components/auth/auth-provider'
import { listMatters, createMatter, type Matter } from '@/lib/matters'
import { Briefcase, Plus, Loader2, ChevronRight, Scale } from 'lucide-react'

export default function MattersPage() {
  const { user } = useAuth()
  const router = useRouter()
  const [matters, setMatters] = useState<Matter[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({ title: '', matter_type: '', court: '', cause_number: '' })

  useEffect(() => {
    if (!user?.id) return
    listMatters(user.id).then((m) => {
      setMatters(m)
      setLoading(false)
    })
  }, [user?.id])

  async function handleCreate() {
    if (!user?.id || !form.title.trim() || saving) return
    setSaving(true)
    const m = await createMatter(user.id, form)
    setSaving(false)
    if (m) router.push(`/matters/${m.id}`)
  }

  return (
    <div className="min-h-screen text-white/90">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
        <div className="flex items-center justify-between gap-3 mb-6">
          <div className="flex items-center gap-2.5">
            <span className="flex items-center justify-center size-9 rounded-lg bg-emerald-500/15 border border-emerald-500/25 text-emerald-400">
              <Briefcase className="size-5" />
            </span>
            <div>
              <h1 className="text-xl font-semibold">Matters</h1>
              <p className="text-[13px] text-white/45">Your cases. Levy remembers each one across chats.</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setCreating((v) => !v)}
            className="flex items-center gap-1.5 rounded-lg bg-emerald-500/90 hover:bg-emerald-500 text-black text-[13px] font-medium px-3 py-2 transition-colors"
          >
            <Plus className="size-4" /> New matter
          </button>
        </div>

        {creating && (
          <div className="mb-6 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.04] p-4">
            <div className="grid sm:grid-cols-2 gap-3">
              <input
                autoFocus
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="Matter title (e.g. Munachonga v Acme Ltd)"
                className="sm:col-span-2 bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-[14px] placeholder:text-white/30 focus:outline-none focus:border-emerald-500/50"
              />
              <input
                value={form.matter_type}
                onChange={(e) => setForm({ ...form, matter_type: e.target.value })}
                placeholder="Type (e.g. Unfair dismissal)"
                className="bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-[14px] placeholder:text-white/30 focus:outline-none focus:border-emerald-500/50"
              />
              <input
                value={form.court}
                onChange={(e) => setForm({ ...form, court: e.target.value })}
                placeholder="Court / division"
                className="bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-[14px] placeholder:text-white/30 focus:outline-none focus:border-emerald-500/50"
              />
              <input
                value={form.cause_number}
                onChange={(e) => setForm({ ...form, cause_number: e.target.value })}
                placeholder="Cause number (if known)"
                className="sm:col-span-2 bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-[14px] placeholder:text-white/30 focus:outline-none focus:border-emerald-500/50"
              />
            </div>
            <div className="flex justify-end gap-2 mt-3">
              <button
                type="button"
                onClick={() => setCreating(false)}
                className="text-[13px] text-white/50 hover:text-white/80 px-3 py-2"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCreate}
                disabled={!form.title.trim() || saving}
                className="flex items-center gap-1.5 rounded-lg bg-emerald-500/90 hover:bg-emerald-500 text-black text-[13px] font-medium px-3 py-2 disabled:opacity-40 transition-colors"
              >
                {saving ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />} Create matter
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <div className="flex items-center gap-2 text-white/40 text-[14px] py-12 justify-center">
            <Loader2 className="size-4 animate-spin" /> Loading your matters…
          </div>
        ) : matters.length === 0 ? (
          <div className="text-center py-16 text-white/40">
            <Scale className="size-8 mx-auto mb-3 opacity-40" />
            <p className="text-[14px]">No matters yet.</p>
            <p className="text-[13px] mt-1">Create one for a case you are running, then chat inside it, Levy will remember the details.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {matters.map((m) => (
              <Link
                key={m.id}
                href={`/matters/${m.id}`}
                className="group flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.02] hover:bg-white/[0.04] hover:border-emerald-500/20 px-4 py-3.5 transition-colors"
              >
                <span className="flex items-center justify-center size-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400/80 flex-shrink-0">
                  <Briefcase className="size-4" />
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-[14px] font-medium text-white/85 truncate">{m.title}</div>
                  <div className="text-[12px] text-white/40 truncate">
                    {[m.matter_type, m.court, m.cause_number].filter(Boolean).join(' · ') || 'No details yet'}
                  </div>
                </div>
                <ChevronRight className="size-4 text-white/25 group-hover:text-emerald-400/70 transition-colors" />
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
