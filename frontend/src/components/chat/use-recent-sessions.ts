'use client'

import { useCallback, useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase'

export interface RecentSession {
  id: string
  title: string
  created_at: string
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
