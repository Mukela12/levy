'use client'

/**
 * Bottom-sheet picker for attaching corpus documents to the current chat.
 *
 * Used by the Paperclip button in the chat input. On mobile this is a true
 * bottom-sheet; on desktop it renders as a centred modal so the chat input
 * doesn't have to grow a popover (keeps the dock visually quiet).
 */

import { useEffect, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  CheckCircle2,
  ExternalLink,
  FileText,
  Loader2,
  Paperclip,
  Search,
  X,
} from 'lucide-react'
import { listDocumentsForUser, type LibraryDocument } from '@/lib/api'

interface AttachmentsSheetProps {
  open: boolean
  onClose: () => void
  userId: string | undefined
  sessionId: string | null | undefined
  /** ids currently attached to the session/staged for the next turn */
  attachedIds: Set<string>
  /** toggle one document — caller decides whether to persist or stage */
  onToggle: (doc: LibraryDocument) => void | Promise<void>
}

export function AttachmentsSheet({
  open,
  onClose,
  userId,
  sessionId,
  attachedIds,
  onToggle,
}: AttachmentsSheetProps) {
  const [docs, setDocs] = useState<LibraryDocument[]>([])
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [busyDoc, setBusyDoc] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (!open || !userId) return
    let cancelled = false
    setLoading(true)
    ;(async () => {
      try {
        const data = await listDocumentsForUser(
          userId,
          sessionId ?? undefined,
        )
        if (cancelled) return
        // Combine global + owned for the picker. Dedupe by id.
        const seen = new Set<string>()
        const merged: LibraryDocument[] = []
        for (const d of [...data.owned, ...data.global]) {
          if (!seen.has(d.id)) {
            seen.add(d.id)
            merged.push(d)
          }
        }
        setDocs(merged)
      } catch {
        setDocs([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, userId, sessionId])

  // Lock scroll while open
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [open])

  const filtered = useMemo(() => {
    if (!query.trim()) return docs
    const q = query.toLowerCase()
    return docs.filter(
      (d) =>
        (d.title || '').toLowerCase().includes(q) ||
        (d.short_name || '').toLowerCase().includes(q),
    )
  }, [docs, query])

  async function handleToggle(doc: LibraryDocument) {
    setBusyDoc((b) => ({ ...b, [doc.id]: true }))
    try {
      await onToggle(doc)
    } finally {
      setBusyDoc((b) => ({ ...b, [doc.id]: false }))
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Sheet body. Bottom-sheet on mobile, centred dialog on md+ */}
          <motion.div
            key="sheet"
            initial={{ y: '100%', opacity: 0.6 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: '100%', opacity: 0.4 }}
            transition={{ type: 'spring', stiffness: 360, damping: 36 }}
            className={[
              'fixed z-50 bg-[#0d0d0f] border border-white/[0.07] flex flex-col',
              // Mobile: bottom-sheet
              'inset-x-0 bottom-0 rounded-t-2xl max-h-[85vh]',
              // Desktop: centred dialog with drop shadow
              'md:left-1/2 md:right-auto md:bottom-auto md:top-[10vh] md:-translate-x-1/2',
              'md:w-[560px] md:rounded-2xl md:max-h-[78vh]',
            ].join(' ')}
            style={{
              boxShadow: '0 32px 64px -16px rgba(0,0,0,0.6)',
              paddingBottom: 'env(safe-area-inset-bottom)',
            }}
          >
            {/* Drag handle (mobile only) */}
            <div className="md:hidden flex items-center justify-center pt-2 pb-1">
              <div className="h-1 w-10 rounded-full bg-white/15" />
            </div>

            {/* Header */}
            <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-white/[0.06]">
              <div className="flex items-center gap-2">
                <span className="flex items-center justify-center size-7 rounded-lg bg-emerald-500/10">
                  <Paperclip size={13} className="text-emerald-400" />
                </span>
                <div>
                  <div className="text-[13px] font-semibold text-white/85">Attach documents</div>
                  <div className="text-[10.5px] text-white/35">
                    Pick from the library or your uploads. Levy will search them in this chat.
                  </div>
                </div>
              </div>
              <button
                onClick={onClose}
                className="p-1.5 rounded-md text-white/30 hover:text-white/60 hover:bg-white/[0.04]"
                aria-label="Close"
              >
                <X size={14} />
              </button>
            </div>

            {/* Filter */}
            <div className="px-4 py-3 border-b border-white/[0.06]">
              <div className="relative">
                <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/25" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Filter documents…"
                  className="w-full pl-9 pr-3 py-2 rounded-lg bg-white/[0.04] border border-white/[0.06] text-[13px] text-white/85 placeholder:text-white/25 focus:outline-none focus:border-emerald-500/30"
                />
              </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto" style={{ overscrollBehavior: 'contain' }}>
              {!userId ? (
                <SignInPrompt onClose={onClose} />
              ) : loading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 size={16} className="text-emerald-400 animate-spin" />
                </div>
              ) : filtered.length === 0 ? (
                <div className="py-12 text-center text-[12.5px] text-white/35 px-6">
                  {query ? 'No matches.' : 'No documents yet.'}
                  {!query && (
                    <p className="mt-2 text-[11.5px] text-white/25">
                      Upload PDFs at <a href="/documents" className="text-emerald-400 hover:underline">Documents</a> to make them searchable.
                    </p>
                  )}
                </div>
              ) : (
                <ul className="px-2 py-2 space-y-1">
                  {filtered.map((doc) => {
                    const isAttached = attachedIds.has(doc.id)
                    return (
                      <li key={doc.id}>
                        <button
                          type="button"
                          onClick={() => handleToggle(doc)}
                          disabled={!!busyDoc[doc.id]}
                          className={`w-full text-left px-3 py-2.5 rounded-xl flex items-start gap-3 transition-colors ${
                            isAttached
                              ? 'bg-emerald-500/[0.08] border border-emerald-500/25'
                              : 'border border-white/[0.05] hover:border-emerald-500/20 hover:bg-emerald-500/[0.04]'
                          }`}
                        >
                          <span className={`flex items-center justify-center size-9 rounded-lg flex-shrink-0 ${doc.is_global ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/15' : 'bg-red-500/10 text-red-400 border border-red-500/20'}`}>
                            <FileText size={15} />
                          </span>
                          <div className="flex-1 min-w-0">
                            <div className="text-[13px] font-medium text-white/85 truncate">{doc.title}</div>
                            <div className="text-[10.5px] text-white/35 mt-0.5 flex items-center gap-1.5">
                              {doc.is_global ? <span>Global library</span> : <span>Your upload</span>}
                              {doc.year ? (
                                <>
                                  <span className="text-white/15">·</span>
                                  <span>{doc.year}</span>
                                </>
                              ) : null}
                              {doc.pdf_page_count ? (
                                <>
                                  <span className="text-white/15">·</span>
                                  <span>{doc.pdf_page_count} pages</span>
                                </>
                              ) : null}
                            </div>
                          </div>
                          <span className={`flex-shrink-0 ${isAttached ? 'text-emerald-400' : 'text-white/15'} mt-1.5`}>
                            {busyDoc[doc.id] ? (
                              <Loader2 size={14} className="animate-spin" />
                            ) : (
                              <CheckCircle2 size={14} />
                            )}
                          </span>
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>

            {/* Footer */}
            <div className="px-4 py-3 border-t border-white/[0.06] flex items-center justify-between">
              <a
                href="/documents"
                className="text-[11.5px] text-white/45 hover:text-emerald-400 inline-flex items-center gap-1"
              >
                Manage documents <ExternalLink size={11} />
              </a>
              <button
                onClick={onClose}
                className="px-3 py-1.5 rounded-md bg-emerald-500/12 border border-emerald-500/20 text-[12px] text-emerald-300 hover:bg-emerald-500/20"
              >
                Done
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

function SignInPrompt({ onClose }: { onClose: () => void }) {
  return (
    <div className="py-12 text-center text-white/55 px-6">
      <Paperclip size={20} className="mx-auto mb-2.5 text-white/25" />
      <p className="text-[13px] text-white/65">Sign in to attach documents</p>
      <p className="text-[11.5px] text-white/30 mt-1.5 max-w-sm mx-auto">
        Anonymous chats can ask questions of the global library, but private uploads and per-chat attachments need an account.
      </p>
      <a
        href="/auth/login"
        onClick={onClose}
        className="mt-4 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-500/12 border border-emerald-500/25 text-[12px] text-emerald-300 hover:bg-emerald-500/20"
      >
        Sign in
      </a>
    </div>
  )
}
