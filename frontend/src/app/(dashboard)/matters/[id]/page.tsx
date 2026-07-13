'use client'

import { use, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/components/auth/auth-provider'
import { createClient } from '@/lib/supabase'
import {
  getMatter, updateMatter, deleteMatter,
  listMatterThreads, listMatterDrafts, setThreadMatter,
  type Matter, type MatterParty, type MatterDate, type MatterThread, type MatterDraft,
} from '@/lib/matters'
import {
  Briefcase, ArrowLeft, Loader2, Plus, X, MessageSquare, FileText,
  Calendar, Users, Trash2, Check, Link2,
} from 'lucide-react'

export default function MatterDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const { user } = useAuth()
  const router = useRouter()
  const [matter, setMatter] = useState<Matter | null>(null)
  const [threads, setThreads] = useState<MatterThread[]>([])
  const [drafts, setDrafts] = useState<MatterDraft[]>([])
  const [loading, setLoading] = useState(true)
  const [savedFlash, setSavedFlash] = useState(false)

  // editable local copies
  const [fields, setFields] = useState({ title: '', matter_type: '', court: '', cause_number: '', facts: '' })
  const [parties, setParties] = useState<MatterParty[]>([])
  const [dates, setDates] = useState<MatterDate[]>([])
  const [newParty, setNewParty] = useState({ role: '', name: '' })
  const [newDate, setNewDate] = useState({ label: '', date: '', note: '' })
  const [linkOpen, setLinkOpen] = useState(false)
  const [unlinked, setUnlinked] = useState<MatterThread[]>([])

  useEffect(() => {
    if (!user?.id) return
    Promise.all([getMatter(id), listMatterThreads(id), listMatterDrafts(id)]).then(([m, t, d]) => {
      if (m) {
        setMatter(m)
        setFields({
          title: m.title || '', matter_type: m.matter_type || '', court: m.court || '',
          cause_number: m.cause_number || '', facts: m.facts || '',
        })
        setParties(m.parties || [])
        setDates(m.key_dates || [])
      }
      setThreads(t)
      setDrafts(d)
      setLoading(false)
    })
  }, [id, user?.id])

  async function persist(patch: Partial<Matter>) {
    await updateMatter(id, patch)
    setSavedFlash(true)
    setTimeout(() => setSavedFlash(false), 1500)
  }

  async function saveDetails() {
    await persist({
      title: fields.title.trim() || 'Untitled matter',
      matter_type: fields.matter_type || null,
      court: fields.court || null,
      cause_number: fields.cause_number || null,
      facts: fields.facts,
    })
  }

  async function addParty() {
    if (!newParty.name.trim()) return
    const next = [...parties, { role: newParty.role.trim() || 'Party', name: newParty.name.trim() }]
    setParties(next); setNewParty({ role: '', name: '' })
    await persist({ parties: next })
  }
  async function removeParty(i: number) {
    const next = parties.filter((_, x) => x !== i)
    setParties(next); await persist({ parties: next })
  }

  async function addDate() {
    if (!newDate.date.trim()) return
    const next = [...dates, { label: newDate.label.trim() || 'Date', date: newDate.date, note: newDate.note.trim() }]
    setDates(next); setNewDate({ label: '', date: '', note: '' })
    await persist({ key_dates: next })
  }
  async function removeDate(i: number) {
    const next = dates.filter((_, x) => x !== i)
    setDates(next); await persist({ key_dates: next })
  }

  async function startChat() {
    if (!user?.id) return
    const supabase = createClient()
    const { data } = await supabase
      .from('chat_sessions')
      .insert({ user_id: user.id, title: fields.title || 'New chat', matter_id: id })
      .select('id')
      .single()
    if (data?.id) router.push(`/chat/${data.id}`)
  }

  async function openLink() {
    setLinkOpen(true)
    const supabase = createClient()
    const { data } = await supabase
      .from('chat_sessions')
      .select('id, title, created_at')
      .eq('user_id', user?.id)
      .is('matter_id', null)
      .order('created_at', { ascending: false })
      .limit(20)
    setUnlinked((data as MatterThread[]) || [])
  }
  async function linkThread(sid: string) {
    await setThreadMatter(sid, id)
    setUnlinked((u) => u.filter((x) => x.id !== sid))
    setThreads(await listMatterThreads(id))
  }
  async function unlinkThread(sid: string) {
    await setThreadMatter(sid, null)
    setThreads((t) => t.filter((x) => x.id !== sid))
  }

  async function handleDelete() {
    if (!confirm('Delete this matter? Your chats and drafts are kept, they are just unlinked from the case.')) return
    await deleteMatter(id)
    router.push('/matters')
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-white/40 text-[14px] py-16 justify-center">
        <Loader2 className="size-4 animate-spin" /> Loading matter…
      </div>
    )
  }
  if (!matter) {
    return (
      <div className="text-center py-16 text-white/40">
        <p>Matter not found.</p>
        <Link href="/matters" className="text-emerald-400 text-[13px] mt-2 inline-block">Back to matters</Link>
      </div>
    )
  }

  const input = "bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-[14px] text-white/90 placeholder:text-white/30 focus:outline-none focus:border-emerald-500/50"
  const card = "rounded-xl border border-white/10 bg-white/[0.02] p-4"
  const label = "text-[11px] font-medium tracking-[0.14em] uppercase text-white/40 flex items-center gap-1.5 mb-2.5"

  return (
    <div className="min-h-screen text-white/90">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6">
        <div className="flex items-center justify-between gap-3 mb-5">
          <Link href="/matters" className="flex items-center gap-1.5 text-[13px] text-white/45 hover:text-white/80">
            <ArrowLeft className="size-4" /> Matters
          </Link>
          <div className="flex items-center gap-3">
            {savedFlash && <span className="flex items-center gap-1 text-[12px] text-emerald-400"><Check className="size-3.5" /> Saved</span>}
            <button onClick={handleDelete} className="text-white/30 hover:text-red-400 transition-colors" aria-label="Delete matter">
              <Trash2 className="size-4" />
            </button>
          </div>
        </div>

        {/* Details */}
        <div className={card + ' mb-4'}>
          <div className="flex items-center gap-2.5 mb-3.5">
            <span className="flex items-center justify-center size-8 rounded-lg bg-emerald-500/15 border border-emerald-500/25 text-emerald-400">
              <Briefcase className="size-4" />
            </span>
            <input
              value={fields.title}
              onChange={(e) => setFields({ ...fields, title: e.target.value })}
              onBlur={saveDetails}
              placeholder="Matter title"
              className="flex-1 bg-transparent text-[17px] font-semibold text-white/90 focus:outline-none border-b border-transparent focus:border-white/10 pb-1"
            />
          </div>
          <div className="grid sm:grid-cols-3 gap-2.5">
            <input value={fields.matter_type} onChange={(e) => setFields({ ...fields, matter_type: e.target.value })} onBlur={saveDetails} placeholder="Type" className={input} />
            <input value={fields.court} onChange={(e) => setFields({ ...fields, court: e.target.value })} onBlur={saveDetails} placeholder="Court / division" className={input} />
            <input value={fields.cause_number} onChange={(e) => setFields({ ...fields, cause_number: e.target.value })} onBlur={saveDetails} placeholder="Cause number" className={input} />
          </div>
        </div>

        {/* Parties */}
        <div className={card + ' mb-4'}>
          <div className={label}><Users className="size-3.5" /> Parties</div>
          <div className="flex flex-col gap-1.5 mb-3">
            {parties.length === 0 && <p className="text-[13px] text-white/30">No parties yet.</p>}
            {parties.map((p, i) => (
              <div key={i} className="flex items-center gap-2 text-[14px]">
                <span className="text-white/85">{p.name}</span>
                <span className="text-[11px] text-emerald-400/70 bg-emerald-500/10 rounded px-1.5 py-0.5">{p.role}</span>
                <button onClick={() => removeParty(i)} className="ml-auto text-white/25 hover:text-red-400"><X className="size-3.5" /></button>
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <input value={newParty.name} onChange={(e) => setNewParty({ ...newParty, name: e.target.value })} placeholder="Name" className={input + ' flex-1'} />
            <input value={newParty.role} onChange={(e) => setNewParty({ ...newParty, role: e.target.value })} placeholder="Role" className={input + ' w-32'} />
            <button onClick={addParty} disabled={!newParty.name.trim()} className="flex items-center rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 px-2.5 disabled:opacity-40"><Plus className="size-4" /></button>
          </div>
        </div>

        {/* Key dates */}
        <div className={card + ' mb-4'}>
          <div className={label}><Calendar className="size-3.5" /> Key dates</div>
          <div className="flex flex-col gap-1.5 mb-3">
            {dates.length === 0 && <p className="text-[13px] text-white/30">No dates yet. Add hearings and filing deadlines here.</p>}
            {dates.map((d, i) => (
              <div key={i} className="flex items-center gap-2 text-[14px]">
                <span className="text-emerald-400/80 font-mono text-[13px] tabular-nums">{d.date}</span>
                <span className="text-white/80">{d.label}</span>
                {d.note && <span className="text-white/35 text-[12px]">— {d.note}</span>}
                <button onClick={() => removeDate(i)} className="ml-auto text-white/25 hover:text-red-400"><X className="size-3.5" /></button>
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <input type="date" value={newDate.date} onChange={(e) => setNewDate({ ...newDate, date: e.target.value })} className={input + ' w-40'} />
            <input value={newDate.label} onChange={(e) => setNewDate({ ...newDate, label: e.target.value })} placeholder="e.g. Hearing" className={input + ' flex-1'} />
            <button onClick={addDate} disabled={!newDate.date} className="flex items-center rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 px-2.5 disabled:opacity-40"><Plus className="size-4" /></button>
          </div>
        </div>

        {/* Facts */}
        <div className={card + ' mb-4'}>
          <div className={label}>Case facts</div>
          <textarea
            value={fields.facts}
            onChange={(e) => setFields({ ...fields, facts: e.target.value })}
            onBlur={saveDetails}
            placeholder="The running story of the case. Levy adds to this as you chat, and reads it in every session so you never have to re-explain."
            rows={5}
            className={input + ' w-full resize-y leading-relaxed'}
          />
        </div>

        {/* Chats in this matter */}
        <div className={card + ' mb-4'}>
          <div className="flex items-center justify-between mb-2.5">
            <div className={label + ' mb-0'}><MessageSquare className="size-3.5" /> Chats in this matter</div>
            <div className="flex gap-2">
              <button onClick={openLink} className="text-[12px] text-white/50 hover:text-white/80 flex items-center gap-1"><Link2 className="size-3.5" /> Link a chat</button>
              <button onClick={startChat} className="text-[12px] text-emerald-400 hover:text-emerald-300 flex items-center gap-1"><Plus className="size-3.5" /> New chat</button>
            </div>
          </div>
          {threads.length === 0 && <p className="text-[13px] text-white/30">No chats yet. Start one, Levy will use this matter's details.</p>}
          <div className="flex flex-col gap-1">
            {threads.map((t) => (
              <div key={t.id} className="flex items-center gap-2 group">
                <Link href={`/chat/${t.id}`} className="flex-1 flex items-center gap-2 text-[14px] text-white/80 hover:text-white py-1.5 min-w-0">
                  <MessageSquare className="size-3.5 text-white/30 flex-shrink-0" />
                  <span className="truncate">{t.title || 'Untitled chat'}</span>
                </Link>
                <button onClick={() => unlinkThread(t.id)} className="text-white/20 hover:text-white/50 opacity-0 group-hover:opacity-100" aria-label="Unlink"><X className="size-3.5" /></button>
              </div>
            ))}
          </div>
          {linkOpen && (
            <div className="mt-3 border-t border-white/10 pt-3">
              <p className="text-[12px] text-white/40 mb-1.5">Link an existing chat to this matter:</p>
              {unlinked.length === 0 ? <p className="text-[12px] text-white/30">No unlinked chats.</p> : (
                <div className="flex flex-col gap-0.5 max-h-48 overflow-auto">
                  {unlinked.map((t) => (
                    <button key={t.id} onClick={() => linkThread(t.id)} className="flex items-center gap-2 text-[13px] text-white/70 hover:text-white hover:bg-white/[0.04] rounded px-2 py-1.5 text-left">
                      <Link2 className="size-3.5 text-white/30" /> <span className="truncate">{t.title || 'Untitled chat'}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Drafts */}
        {drafts.length > 0 && (
          <div className={card}>
            <div className={label}><FileText className="size-3.5" /> Drafts in this matter</div>
            <div className="flex flex-col gap-1">
              {drafts.map((d) => (
                <div key={d.id} className="flex items-center gap-2 text-[14px] text-white/80 py-1">
                  <FileText className="size-3.5 text-emerald-400/50" />
                  <span className="truncate">{d.title}</span>
                  <span className="text-[11px] text-white/30 uppercase ml-auto">{d.kind}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
