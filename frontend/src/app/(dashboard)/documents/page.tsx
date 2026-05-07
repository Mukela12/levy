'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '@/components/auth/auth-provider'
import { usePdfViewer } from '@/components/chat/pdf-viewer-context'
import {
  attachDocumentToSession,
  detachDocumentFromSession,
  listDocumentsForUser,
  uploadDocument,
  type DocumentsByVisibility,
  type LibraryDocument,
} from '@/lib/api'
import {
  BookOpen,
  ExternalLink,
  FileText,
  Loader2,
  Paperclip,
  Search,
  Upload,
  UserRound,
  X,
} from 'lucide-react'

type Section = 'global' | 'owned'

function formatPages(n?: number): string {
  if (!n) return '—'
  return `${n} page${n === 1 ? '' : 's'}`
}

function formatChunks(n?: number): string {
  if (!n) return '—'
  return `${n} chunk${n === 1 ? '' : 's'}`
}

function DocumentRow({
  doc,
  onOpen,
  rightSlot,
}: {
  doc: LibraryDocument
  onOpen: () => void
  rightSlot?: React.ReactNode
}) {
  return (
    <div className="group flex items-center gap-3 px-3.5 py-3 rounded-xl border border-white/[0.06] bg-white/[0.02] hover:border-emerald-500/15 hover:bg-emerald-500/[0.02] transition-colors">
      <button
        type="button"
        onClick={onOpen}
        className="flex items-center gap-3 flex-1 min-w-0 text-left"
      >
        <span className="flex items-center justify-center size-9 rounded-lg bg-red-500/10 border border-red-500/20 flex-shrink-0">
          <FileText size={15} className="text-red-400" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-medium text-white/85 truncate">{doc.title}</div>
          <div className="text-[11px] text-white/30 mt-0.5 flex items-center gap-1.5">
            {doc.year ? <span>{doc.year}</span> : null}
            {doc.year ? <span className="text-white/15">·</span> : null}
            <span>{formatPages(doc.pdf_page_count)}</span>
            <span className="text-white/15">·</span>
            <span>{formatChunks(doc.total_chunks)}</span>
          </div>
        </div>
      </button>
      <div className="flex items-center gap-2 flex-shrink-0">{rightSlot}</div>
    </div>
  )
}

export default function DocumentsPage() {
  const { user, session } = useAuth()
  const pdf = usePdfViewer()
  const [data, setData] = useState<DocumentsByVisibility | null>(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [section, setSection] = useState<Section>('global')
  const [query, setQuery] = useState('')
  const [attaching, setAttaching] = useState<Record<string, boolean>>({})
  const [recentSessionId, setRecentSessionId] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Resolve the most recent chat session so the user can attach uploads to a
  // thread directly from the documents page. (We don't know which thread is
  // "active" from this route, so we offer the latest one as the default.)
  useEffect(() => {
    if (!user?.id) return
    ;(async () => {
      try {
        const { createClient } = await import('@/lib/supabase')
        const supabase = createClient()
        const { data } = await supabase
          .from('chat_sessions')
          .select('id')
          .eq('user_id', user.id)
          .order('created_at', { ascending: false })
          .limit(1)
        if (data && data[0]) setRecentSessionId(data[0].id)
      } catch {
        // optional — attach UI just won't show
      }
    })()
  }, [user?.id])

  async function reload() {
    if (!user?.id) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const res = await listDocumentsForUser(user.id, recentSessionId ?? undefined)
      setData(res)
    } catch {
      setData({ global: [], owned: [], attached: [], counts: { global: 0, owned: 0, attached: 0 } })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, recentSessionId])

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      await uploadDocument(file, session?.access_token, user?.id)
      await reload()
      setSection('owned')
    } catch {
      // surfaced via the loading state for now
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function handleAttachToggle(doc: LibraryDocument) {
    if (!recentSessionId) return
    const isAttached = data?.attached.some((d) => d.id === doc.id)
    setAttaching((prev) => ({ ...prev, [doc.id]: true }))
    try {
      if (isAttached) {
        await detachDocumentFromSession(recentSessionId, doc.id)
      } else {
        await attachDocumentToSession(recentSessionId, doc.id)
      }
      await reload()
    } catch {
      // ignore
    } finally {
      setAttaching((prev) => ({ ...prev, [doc.id]: false }))
    }
  }

  const visible = useMemo(() => {
    if (!data) return []
    const list = section === 'global' ? data.global : data.owned
    if (!query.trim()) return list
    const q = query.toLowerCase()
    return list.filter(
      (d) => (d.title || '').toLowerCase().includes(q) || (d.short_name || '').toLowerCase().includes(q),
    )
  }, [data, section, query])

  const attachedIds = useMemo(
    () => new Set((data?.attached ?? []).map((d) => d.id)),
    [data?.attached],
  )

  return (
    <div className="flex-1 overflow-y-auto" style={{ overscrollBehavior: 'none' }}>
      <div className="px-6 py-6 max-w-5xl mx-auto w-full">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 mb-6">
          <div>
            <h1
              className="text-2xl font-bold text-white/90 tracking-tight"
              style={{ fontFamily: "'Playfair Display', serif" }}
            >
              Documents
            </h1>
            <p className="text-[12px] text-white/35 mt-1">
              The curated Zambian-law library is always available. Upload your own to make them searchable
              for you, or attach them to a thread for one-off context.
            </p>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            onChange={handleUpload}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading || !user}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-[13px] font-medium text-white transition-all disabled:opacity-50"
            style={{
              background: 'linear-gradient(180deg, rgb(16 185 129) 0%, rgb(5 150 105) 100%)',
              boxShadow:
                '0 1px 0 0 rgba(255,255,255,0.18) inset, 0 0 0 1px rgba(16,185,129,0.45), 0 8px 20px -8px rgba(16,185,129,0.55)',
            }}
          >
            {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
            <span>{uploading ? 'Uploading…' : 'Upload PDF'}</span>
          </button>
        </div>

        {/* Section tabs + search */}
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <SectionTab
            active={section === 'global'}
            onClick={() => setSection('global')}
            Icon={BookOpen}
            label="Global library"
            count={data?.counts.global}
          />
          <SectionTab
            active={section === 'owned'}
            onClick={() => setSection('owned')}
            Icon={UserRound}
            label="My uploads"
            count={data?.counts.owned}
          />
          <div className="flex-1 min-w-[200px] max-w-sm relative">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/25" />
            <input
              type="text"
              placeholder="Filter by name…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.06] text-[12.5px] text-white/85 placeholder:text-white/20 focus:outline-none focus:border-emerald-500/30 transition-colors"
            />
          </div>
        </div>

        {/* This-thread strip */}
        {recentSessionId && (data?.attached.length ?? 0) > 0 && (
          <div className="mb-5 rounded-xl px-4 py-3 border border-emerald-500/20 bg-emerald-500/[0.04]">
            <div className="text-[10.5px] font-bold tracking-[0.18em] uppercase text-emerald-400 mb-2">
              Attached to your most recent thread
            </div>
            <div className="flex flex-wrap gap-2">
              {data!.attached.map((d) => (
                <button
                  key={d.id}
                  type="button"
                  onClick={() => handleAttachToggle(d)}
                  disabled={!!attaching[d.id]}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-[11.5px] text-emerald-100/90 hover:bg-emerald-500/20 transition-colors"
                >
                  <Paperclip size={11} />
                  <span className="max-w-[180px] truncate">{d.title}</span>
                  {attaching[d.id] ? <Loader2 size={11} className="animate-spin" /> : <X size={11} />}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Body */}
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="size-5 text-emerald-400 animate-spin" />
          </div>
        ) : visible.length === 0 ? (
          <EmptyState section={section} hasUser={!!user} />
        ) : (
          <div className="space-y-1.5">
            {visible.map((doc) => (
              <DocumentRow
                key={doc.id}
                doc={doc}
                onOpen={() =>
                  pdf.open({
                    documentId: doc.id,
                    actName: doc.short_name || doc.title,
                    pageStart: 1,
                  })
                }
                rightSlot={
                  <>
                    {recentSessionId && (
                      <button
                        type="button"
                        onClick={() => handleAttachToggle(doc)}
                        disabled={!!attaching[doc.id]}
                        className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] transition-colors ${
                          attachedIds.has(doc.id)
                            ? 'bg-emerald-500/15 border border-emerald-500/25 text-emerald-400'
                            : 'bg-white/[0.04] border border-white/[0.06] text-white/55 hover:text-white/85 hover:border-white/[0.12]'
                        }`}
                      >
                        {attaching[doc.id] ? (
                          <Loader2 size={11} className="animate-spin" />
                        ) : (
                          <Paperclip size={11} />
                        )}
                        <span>{attachedIds.has(doc.id) ? 'Attached' : 'Attach'}</span>
                      </button>
                    )}
                    {doc.canonical_url && (
                      <a
                        href={doc.canonical_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="text-white/25 hover:text-white/60 transition-colors p-1"
                        title="Open canonical source"
                      >
                        <ExternalLink size={13} />
                      </a>
                    )}
                  </>
                }
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function SectionTab({
  active,
  onClick,
  Icon,
  label,
  count,
}: {
  active: boolean
  onClick: () => void
  Icon: typeof BookOpen
  label: string
  count?: number
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[12.5px] transition-colors border ${
        active
          ? 'bg-emerald-500/10 border-emerald-500/25 text-emerald-200'
          : 'bg-white/[0.02] border-white/[0.06] text-white/55 hover:text-white/85 hover:border-white/[0.12]'
      }`}
    >
      <Icon size={13} />
      <span>{label}</span>
      {typeof count === 'number' && (
        <span className={`text-[10px] ${active ? 'text-emerald-300/80' : 'text-white/30'}`}>
          {count}
        </span>
      )}
    </button>
  )
}

function EmptyState({ section, hasUser }: { section: Section; hasUser: boolean }) {
  if (!hasUser) {
    return (
      <p className="text-[12.5px] text-white/35 py-12 text-center">
        Sign in to upload your own documents.
      </p>
    )
  }
  if (section === 'global') {
    return (
      <p className="text-[12.5px] text-white/35 py-12 text-center">
        The global library is empty.
      </p>
    )
  }
  return (
    <div className="py-12 text-center text-white/40">
      <Upload size={20} className="mx-auto mb-2.5 text-white/25" />
      <p className="text-[13px]">You haven&apos;t uploaded any documents yet.</p>
      <p className="text-[11.5px] text-white/25 mt-1">
        Upload a PDF and it becomes searchable for you across all chats.
      </p>
    </div>
  )
}
