import { createClient } from '@/lib/supabase'

// A Matter is a persistent case container: parties, court, cause number, a
// running facts summary, key dates, and the chat threads + drafts for the case.
// Rows are owner-scoped by RLS (owner_id = auth.uid()), read/written directly
// from the browser like chat_sessions.

export interface MatterParty {
  role: string
  name: string
}

export interface MatterDate {
  label: string
  date: string
  note?: string
}

export interface Matter {
  id: string
  owner_id: string
  title: string
  matter_type?: string | null
  court?: string | null
  cause_number?: string | null
  parties?: MatterParty[]
  facts?: string | null
  key_dates?: MatterDate[]
  status?: string
  created_at?: string
  updated_at?: string
}

export async function listMatters(userId: string): Promise<Matter[]> {
  const supabase = createClient()
  const { data } = await supabase
    .from('matters')
    .select('*')
    .eq('owner_id', userId)
    .order('updated_at', { ascending: false })
  return (data as Matter[]) || []
}

export async function getMatter(id: string): Promise<Matter | null> {
  const supabase = createClient()
  const { data } = await supabase.from('matters').select('*').eq('id', id).maybeSingle()
  return (data as Matter) || null
}

export async function createMatter(userId: string, m: Partial<Matter>): Promise<Matter | null> {
  const supabase = createClient()
  const { data } = await supabase
    .from('matters')
    .insert({
      owner_id: userId,
      title: (m.title || 'Untitled matter').trim(),
      matter_type: m.matter_type || null,
      court: m.court || null,
      cause_number: m.cause_number || null,
      parties: m.parties || [],
      facts: m.facts || '',
      key_dates: m.key_dates || [],
    })
    .select()
    .single()
  return (data as Matter) || null
}

export async function updateMatter(id: string, patch: Partial<Matter>): Promise<void> {
  const supabase = createClient()
  await supabase
    .from('matters')
    .update({ ...patch, updated_at: new Date().toISOString() })
    .eq('id', id)
}

export async function deleteMatter(id: string): Promise<void> {
  const supabase = createClient()
  await supabase.from('matters').delete().eq('id', id)
}

// Threads (chat sessions) linked to a matter.
export interface MatterThread {
  id: string
  title: string | null
  created_at: string
}

export async function listMatterThreads(matterId: string): Promise<MatterThread[]> {
  const supabase = createClient()
  const { data } = await supabase
    .from('chat_sessions')
    .select('id, title, created_at')
    .eq('matter_id', matterId)
    .order('created_at', { ascending: false })
  return (data as MatterThread[]) || []
}

export async function setThreadMatter(sessionId: string, matterId: string | null): Promise<void> {
  const supabase = createClient()
  await supabase.from('chat_sessions').update({ matter_id: matterId }).eq('id', sessionId)
}

// Drafts (artifacts) linked to a matter.
export interface MatterDraft {
  id: string
  title: string
  kind: string
  created_at: string
}

export async function listMatterDrafts(matterId: string): Promise<MatterDraft[]> {
  const supabase = createClient()
  const { data } = await supabase
    .from('artifacts')
    .select('id, title, kind, created_at')
    .eq('matter_id', matterId)
    .order('created_at', { ascending: false })
  return (data as MatterDraft[]) || []
}
