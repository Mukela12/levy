'use client'

import { useCallback, useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase'

export interface RecentSession {
  id: string
  title: string
  created_at: string
}

export function useChatTitle(userId: string | undefined, sessionId: string) {
  const [named, setNamed] = useState<{ sessionId: string; title: string } | null>(null)
  useEffect(() => {
    if (!userId) return
    let active = true
    const load = async () => {
      const { data } = await createClient().from('chat_sessions').select('title').eq('id', sessionId).eq('user_id', userId).maybeSingle()
      if (active && data?.title) setNamed({ sessionId, title: data.title })
    }
    void load()
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') void load() }, 30000)
    return () => { active = false; window.clearInterval(timer) }
  }, [userId, sessionId])
  return userId && named?.sessionId === sessionId ? named.title : 'Conversation'
}

/**
 * The signed-in user's recent chats, shared by both presentations of the
 * sidebar so the query and the delete path live in one place.
 */
export function useRecentSessions(userId: string | undefined, pathname: string) {
  const [sessions, setSessions] = useState<RecentSession[]>([])

  const load = useCallback(async () => {
    if (!userId) return
    const supabase = createClient()
    const { data } = await supabase
      .from('chat_sessions')
      .select('id, title, created_at')
      .eq('user_id', userId)
      .order('created_at', { ascending: false })
      .limit(20)
    if (data) setSessions(data)
  }, [userId])

  useEffect(() => {
    if (userId) void load()
    else setSessions([])
  }, [userId, load])

  // The server names the first exchange after saving it. Refresh quietly so a
  // generated title arrives without a full reload or an enabled realtime feed.
  useEffect(() => {
    if (!userId) return
    const refresh = () => { if (document.visibilityState === 'visible') void load() }
    const timer = window.setInterval(refresh, 30000)
    window.addEventListener('focus', refresh)
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [userId, load])

  // Pull in a freshly created chat so it appears the moment the user lands on
  // its route, without waiting for a refresh.
  useEffect(() => {
    const match = pathname.match(/^\/chat\/([^/]+)$/)
    if (match && userId && !sessions.some((s) => s.id === match[1])) void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, userId])

  const remove = useCallback(async (id: string) => {
    const supabase = createClient()
    await supabase.from('chat_messages').delete().eq('session_id', id)
    await supabase.from('chat_sessions').delete().eq('id', id)
    setSessions((prev) => prev.filter((s) => s.id !== id))
  }, [])

  return { sessions, reload: load, remove }
}

export function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${Math.max(mins, 0)}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}
