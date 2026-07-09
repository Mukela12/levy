'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  attachDocumentToSession,
  detachDocumentFromSession,
  listSessionDocuments,
  type LibraryDocument,
} from '@/lib/api'

/**
 * Lightweight hook for tracking a chat session's attached documents.
 *
 * The chat page passes the resulting `attachedDocIds` array to streamQuery so
 * the agent's corpus search includes those documents alongside the global
 * library + the user's own uploads.
 */
export function useSessionAttachments(sessionId: string | null) {
  const [attached, setAttached] = useState<LibraryDocument[]>([])
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    if (!sessionId) {
      setAttached([])
      return
    }
    setLoading(true)
    try {
      const r = await listSessionDocuments(sessionId)
      setAttached(r.documents)
    } catch {
      setAttached([])
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => {
    refresh()
  }, [refresh])

  const attach = useCallback(
    async (documentId: string) => {
      if (!sessionId) return
      await attachDocumentToSession(sessionId, documentId)
      await refresh()
    },
    [sessionId, refresh],
  )

  const detach = useCallback(
    async (documentId: string) => {
      if (!sessionId) return
      await detachDocumentFromSession(sessionId, documentId)
      await refresh()
    },
    [sessionId, refresh],
  )

  return {
    attached,
    attachedIds: attached.map((d) => d.id),
    loading,
    attach,
    detach,
    refresh,
  }
}
