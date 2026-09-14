'use client'

/**
 * Which sessions are waiting on the person to answer a clarifying question.
 * Kept in localStorage so the sidebar can show the amber dot across reloads
 * on this device; the server-persisted ask_user block remains the durable
 * record inside the thread itself.
 */

import { useSyncExternalStore } from 'react'

const KEY = 'levy-awaiting-v1'
const EVENT = 'levy-awaiting-change'

function read(): string[] {
  try {
    const raw = window.localStorage.getItem(KEY)
    const v = raw ? JSON.parse(raw) : []
    return Array.isArray(v) ? v.filter((x) => typeof x === 'string') : []
  } catch {
    return []
  }
}

let cachedRaw: string | null | undefined
let cached: string[] = []
function snapshot(): string[] {
  let raw: string | null = null
  try {
    raw = window.localStorage.getItem(KEY)
  } catch {
    raw = null
  }
  if (raw === cachedRaw) return cached
  cachedRaw = raw
  cached = read()
  return cached
}

function write(ids: string[]) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(ids.slice(-50)))
  } catch {
    cachedRaw = JSON.stringify(ids)
    cached = ids
  }
  window.dispatchEvent(new Event(EVENT))
}

export function markAwaiting(sessionId: string) {
  const ids = snapshot()
  if (!ids.includes(sessionId)) write([...ids, sessionId])
}

export function clearAwaiting(sessionId: string) {
  const ids = snapshot()
  if (ids.includes(sessionId)) write(ids.filter((id) => id !== sessionId))
}

function subscribe(cb: () => void) {
  window.addEventListener('storage', cb)
  window.addEventListener(EVENT, cb)
  return () => {
    window.removeEventListener('storage', cb)
    window.removeEventListener(EVENT, cb)
  }
}

const EMPTY: string[] = []

export function useAwaitingSessions(): string[] {
  return useSyncExternalStore(subscribe, snapshot, () => EMPTY)
}
