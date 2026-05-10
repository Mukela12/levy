'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '@/components/auth/auth-provider'
import { usePdfViewer } from '@/components/chat/pdf-viewer-context'
import { FolderCard } from '@/components/documents/folder-card'
import {
  attachDocumentToSession,
  createFolder,
  deleteFolder,
  detachDocumentFromSession,
  listDocumentsForUser,
  listFolders,
  moveDocumentToFolder,
  renameFolder,
  uploadDocument,
  type DocumentsByVisibility,
  type FolderRow,
  type LibraryDocument,
} from '@/lib/api'
import {
  ChevronRight,
  ExternalLink,
  FileText,
  Loader2,
  Paperclip,
  Pencil,
  Plus,
  Search,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { CTA } from '@/components/ui/cta'

// Sentinel ids used to address the two non-user-folder pseudo-folders.
const FOLDER_GLOBAL = '__global__'
const FOLDER_UNFILED = '__unfiled__'

type FolderId = string // user folder uuid OR one of the sentinels above

function formatPages(n?: number) {
  return n ? `${n} page${n === 1 ? '' : 's'}` : '-'
}
function formatChunks(n?: number) {
  return n ? `${n} chunk${n === 1 ? '' : 's'}` : '-'
}

export default function DocumentsPage() {
  const { user, session } = useAuth()
  const pdf = usePdfViewer()
  const [activeFolder, setActiveFolder] = useState<FolderId | null>(null)
  const [data, setData] = useState<DocumentsByVisibility | null>(null)
  const [folders, setFolders] = useState<FolderRow[]>([])
  const [unfiledCount, setUnfiledCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [creatingFolder, setCreatingFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [renameTarget, setRenameTarget] = useState<FolderRow | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [busyDoc, setBusyDoc] = useState<Record<string, boolean>>({})
  const [recentSessionId, setRecentSessionId] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Resolve the user's most recent thread (used as the default attach target
  // when the user is browsing /documents directly).
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
        // optional
      }
    })()
  }, [user?.id])

  async function reloadAll() {
    if (!user?.id) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const folderId =
        activeFolder === FOLDER_GLOBAL
          ? null
          : activeFolder === FOLDER_UNFILED
          ? 'unfiled'
          : activeFolder ?? null
      const [docs, folderRes] = await Promise.all([
        listDocumentsForUser(user.id, recentSessionId ?? undefined, folderId ?? undefined),
        listFolders(user.id),
      ])
      setData(docs)
      setFolders(folderRes.folders)
      setUnfiledCount(folderRes.unfiled_count)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    reloadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, recentSessionId, activeFolder])

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const folderId =
        activeFolder &&
        activeFolder !== FOLDER_GLOBAL &&
        activeFolder !== FOLDER_UNFILED
          ? activeFolder
          : null
      await uploadDocument(file, session?.access_token, user?.id, folderId)
      await reloadAll()
    } catch {
      // surfaced via reload state
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function handleCreateFolder() {
    if (!user?.id) return
    const name = newFolderName.trim()
    if (!name) return
    try {
      await createFolder(user.id, name)
      setNewFolderName('')
      setCreatingFolder(false)
      await reloadAll()
    } catch {
      // collision (unique name) - keep dialog open
    }
  }

  async function handleRenameFolder() {
    if (!renameTarget) return
    const name = renameValue.trim()
    if (!name) return
    try {
      await renameFolder(renameTarget.id, name)
      setRenameTarget(null)
      setRenameValue('')
      await reloadAll()
    } catch {
      // ignore
    }
  }

  async function handleDeleteFolder(folder: FolderRow) {
    const ok = window.confirm(
      `Delete folder "${folder.name}"? Documents inside will become unfiled (still searchable). To delete the folder AND its documents, click Cancel and use Shift+click.`,
    )
    if (!ok) return
    try {
      await deleteFolder(folder.id, false)
      if (activeFolder === folder.id) setActiveFolder(null)
      await reloadAll()
    } catch {
      // ignore
    }
  }

  async function handleAttachToggle(doc: LibraryDocument) {
    if (!recentSessionId) return
    setBusyDoc((b) => ({ ...b, [doc.id]: true }))
    try {
      const isAttached = data?.attached.some((d) => d.id === doc.id)
      if (isAttached) await detachDocumentFromSession(recentSessionId, doc.id)
      else await attachDocumentToSession(recentSessionId, doc.id)
      await reloadAll()
    } finally {
      setBusyDoc((b) => ({ ...b, [doc.id]: false }))
    }
  }

  async function handleMoveToFolder(doc: LibraryDocument, folderId: string | null) {
    setBusyDoc((b) => ({ ...b, [doc.id]: true }))
    try {
      await moveDocumentToFolder(doc.id, folderId)
      await reloadAll()
    } finally {
      setBusyDoc((b) => ({ ...b, [doc.id]: false }))
    }
  }

  // ── Resolved view state ─────────────────────────────────────────────────
  const docs = useMemo(() => {
    if (!data) return []
    if (activeFolder === FOLDER_GLOBAL) return data.global
    return data.owned
  }, [data, activeFolder])

  const filteredDocs = useMemo(() => {
    if (!query.trim()) return docs
    const q = query.toLowerCase()
    return docs.filter(
      (d) => (d.title || '').toLowerCase().includes(q) || (d.short_name || '').toLowerCase().includes(q),
    )
  }, [docs, query])

  const attachedIds = useMemo(
    () => new Set((data?.attached ?? []).map((d) => d.id)),
    [data?.attached],
  )

  const activeFolderRow: FolderRow | null = useMemo(() => {
    if (!activeFolder) return null
    if (activeFolder === FOLDER_GLOBAL || activeFolder === FOLDER_UNFILED) return null
    return folders.find((f) => f.id === activeFolder) ?? null
  }, [activeFolder, folders])

  const activeFolderTitle =
    activeFolder === FOLDER_GLOBAL
      ? 'Global library'
      : activeFolder === FOLDER_UNFILED
      ? 'Unfiled uploads'
      : activeFolderRow?.name ?? ''

  const isUserFolder =
    !!activeFolder && activeFolder !== FOLDER_GLOBAL && activeFolder !== FOLDER_UNFILED

  return (
    <div className="flex-1 overflow-y-auto" style={{ overscrollBehavior: 'none' }}>
      <div className="px-6 py-6 max-w-5xl mx-auto w-full">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 mb-6">
          <div>
            <h1
              className="text-2xl font-bold text-white/90 tracking-tight"
              style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
            >
              Documents
            </h1>
            <p className="text-[12px] text-white/35 mt-1">
              {activeFolder
                ? activeFolder === FOLDER_GLOBAL
                  ? 'Curated Zambian-law library, available in every chat.'
                  : 'All uploads are searchable across your chats. Use folders to organise them.'
                : 'Browse the curated library or organise your own uploads into folders.'}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <input ref={fileInputRef} type="file" accept=".pdf" onChange={handleUpload} className="hidden" />
            {activeFolder && activeFolder !== FOLDER_GLOBAL && (
              <>
                <CTA
                  size="md"
                  tone="primary"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading || !user}
                  iconOnly
                  startIcon={uploading ? <Loader2 className="animate-spin" /> : <Upload />}
                  aria-label={uploading ? 'Uploading' : 'Upload PDF'}
                  className="sm:hidden"
                />
                <CTA
                  size="md"
                  tone="primary"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading || !user}
                  startIcon={uploading ? <Loader2 className="animate-spin" /> : <Upload />}
                  className="hidden sm:inline-flex"
                >
                  {uploading ? 'Uploading' : 'Upload'}
                </CTA>
              </>
            )}
          </div>
        </div>

        {/* Breadcrumb when inside a folder */}
        {activeFolder && (
          <div className="flex items-center gap-1.5 mb-5 text-[12.5px]">
            <button
              onClick={() => setActiveFolder(null)}
              className="text-white/35 hover:text-emerald-400 transition-colors"
            >
              Documents
            </button>
            <ChevronRight size={11} className="text-white/15" />
            <span className="text-white/75">{activeFolderTitle}</span>
            <button
              onClick={() => setActiveFolder(null)}
              className="ml-2 p-1 rounded hover:bg-white/[0.05] text-white/25 hover:text-white/55 transition-colors"
              aria-label="Back"
            >
              <X size={12} />
            </button>
            {activeFolderRow && (
              <div className="ml-auto flex items-center gap-1">
                <button
                  onClick={() => {
                    setRenameTarget(activeFolderRow)
                    setRenameValue(activeFolderRow.name)
                  }}
                  className="flex items-center gap-1 px-2 py-1 rounded text-[11px] text-white/40 hover:text-white/70 hover:bg-white/[0.04]"
                >
                  <Pencil size={11} /> Rename
                </button>
                <button
                  onClick={() => handleDeleteFolder(activeFolderRow)}
                  className="flex items-center gap-1 px-2 py-1 rounded text-[11px] text-white/40 hover:text-red-400 hover:bg-red-500/[0.06]"
                >
                  <Trash2 size={11} /> Delete folder
                </button>
              </div>
            )}
          </div>
        )}

        {/* Folder grid */}
        {!activeFolder && (
          <>
            {loading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="size-5 text-emerald-400 animate-spin" />
              </div>
            ) : (
              <div className="grid grid-cols-2 lg:grid-cols-3 gap-2.5 sm:gap-3 mb-8">
                <FolderCard
                  kind="global"
                  name="Global library"
                  description={`${data?.counts.global ?? 0} curated Zambian-law documents`}
                  onClick={() => setActiveFolder(FOLDER_GLOBAL)}
                />
                {folders.map((f) => (
                  <div key={f.id} className="relative">
                    <FolderCard kind="user" name={f.name} count={f.doc_count} onClick={() => setActiveFolder(f.id)} />
                  </div>
                ))}
                {unfiledCount > 0 && (
                  <FolderCard
                    kind="user"
                    name="Unfiled uploads"
                    count={unfiledCount}
                    onClick={() => setActiveFolder(FOLDER_UNFILED)}
                  />
                )}
                <FolderCard
                  kind="new"
                  name="New folder"
                  description="Group related uploads. Chat still searches all of them."
                  onClick={() => setCreatingFolder(true)}
                />
              </div>
            )}
          </>
        )}

        {/* Folder detail (document list) */}
        {activeFolder && (
          <>
            {/* Filter input */}
            <div className="relative max-w-sm mb-4">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/25" />
              <input
                type="text"
                placeholder="Filter by name…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.06] text-[12.5px] text-white/85 placeholder:text-white/20 focus:outline-none focus:border-emerald-500/30 transition-colors"
              />
            </div>

            {loading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="size-5 text-emerald-400 animate-spin" />
              </div>
            ) : filteredDocs.length === 0 ? (
              <EmptyFolder
                isGlobal={activeFolder === FOLDER_GLOBAL}
                isUserFolder={isUserFolder}
                onUpload={() => fileInputRef.current?.click()}
              />
            ) : (
              <div className="space-y-1.5">
                {filteredDocs.map((doc) => {
                  const isOwned = !!doc.owner_id && doc.owner_id === user?.id
                  return (
                    <div
                      key={doc.id}
                      className="group flex items-center gap-3 px-3.5 py-3 rounded-xl border border-white/[0.06] bg-white/[0.02] hover:border-emerald-500/15 hover:bg-emerald-500/[0.02] transition-colors"
                    >
                      <button
                        type="button"
                        onClick={() =>
                          pdf.open({
                            documentId: doc.id,
                            actName: doc.short_name || doc.title,
                            pageStart: 1,
                          })
                        }
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
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        {isOwned && folders.length > 0 && (
                          <select
                            value={doc.folder_id ?? ''}
                            onChange={(e) =>
                              handleMoveToFolder(doc, e.target.value === '' ? null : e.target.value)
                            }
                            disabled={!!busyDoc[doc.id]}
                            className="px-2 py-1.5 rounded-md bg-white/[0.04] border border-white/[0.06] text-[11px] text-white/65 hover:border-white/[0.12] disabled:opacity-50 focus:outline-none focus:border-emerald-500/30"
                          >
                            <option value="">Unfiled</option>
                            {folders.map((f) => (
                              <option key={f.id} value={f.id}>
                                {f.name}
                              </option>
                            ))}
                          </select>
                        )}
                        {recentSessionId && (
                          <button
                            type="button"
                            onClick={() => handleAttachToggle(doc)}
                            disabled={!!busyDoc[doc.id]}
                            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] transition-colors ${
                              attachedIds.has(doc.id)
                                ? 'bg-emerald-500/15 border border-emerald-500/25 text-emerald-400'
                                : 'bg-white/[0.04] border border-white/[0.06] text-white/55 hover:text-white/85 hover:border-white/[0.12]'
                            }`}
                          >
                            {busyDoc[doc.id] ? (
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
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </>
        )}
      </div>

      {/* New folder modal */}
      {creatingFolder && (
        <Modal onClose={() => setCreatingFolder(false)} title="New folder">
          <input
            autoFocus
            type="text"
            placeholder="Folder name"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleCreateFolder()
            }}
            className="w-full px-3 py-2 rounded-lg bg-white/[0.04] border border-white/[0.08] text-[13px] text-white/85 focus:outline-none focus:border-emerald-500/40"
          />
          <div className="mt-3 flex justify-end gap-2">
            <button
              onClick={() => setCreatingFolder(false)}
              className="px-3 py-1.5 rounded-md text-[12px] text-white/55 hover:text-white/85"
            >
              Cancel
            </button>
            <button
              onClick={handleCreateFolder}
              disabled={!newFolderName.trim()}
              className="px-3 py-1.5 rounded-md bg-emerald-500/15 border border-emerald-500/25 text-[12px] text-emerald-300 disabled:opacity-50"
            >
              Create
            </button>
          </div>
        </Modal>
      )}

      {/* Rename folder modal */}
      {renameTarget && (
        <Modal onClose={() => setRenameTarget(null)} title="Rename folder">
          <input
            autoFocus
            type="text"
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleRenameFolder()
            }}
            className="w-full px-3 py-2 rounded-lg bg-white/[0.04] border border-white/[0.08] text-[13px] text-white/85 focus:outline-none focus:border-emerald-500/40"
          />
          <div className="mt-3 flex justify-end gap-2">
            <button
              onClick={() => setRenameTarget(null)}
              className="px-3 py-1.5 rounded-md text-[12px] text-white/55 hover:text-white/85"
            >
              Cancel
            </button>
            <button
              onClick={handleRenameFolder}
              className="px-3 py-1.5 rounded-md bg-emerald-500/15 border border-emerald-500/25 text-[12px] text-emerald-300"
            >
              Save
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function Modal({
  children,
  onClose,
  title,
}: {
  children: React.ReactNode
  onClose: () => void
  title: string
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div
        className="relative w-full max-w-sm rounded-xl border border-white/[0.08] bg-[#0d0d0f] p-4"
        style={{ boxShadow: '0 32px 64px -16px rgba(0,0,0,0.6)' }}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-[13px] font-semibold text-white/85">{title}</h3>
          <button onClick={onClose} className="text-white/30 hover:text-white/60 p-1" aria-label="Close">
            <X size={14} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

function EmptyFolder({
  isGlobal,
  isUserFolder,
  onUpload,
}: {
  isGlobal: boolean
  isUserFolder: boolean
  onUpload: () => void
}) {
  if (isGlobal) {
    return (
      <p className="text-[12.5px] text-white/35 py-12 text-center">The global library is empty.</p>
    )
  }
  return (
    <div className="py-12 text-center text-white/45">
      <Upload size={20} className="mx-auto mb-2.5 text-white/25" />
      <p className="text-[13px] text-white/65">
        {isUserFolder ? 'This folder is empty.' : 'No unfiled uploads.'}
      </p>
      <p className="text-[11.5px] text-white/30 mt-1">
        Upload PDFs to make them searchable across all your chats.
      </p>
      <button
        onClick={onUpload}
        className="mt-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-emerald-500/12 border border-emerald-500/25 text-[12px] text-emerald-300 hover:bg-emerald-500/18"
      >
        <Plus size={12} /> Upload PDF
      </button>
    </div>
  )
}
