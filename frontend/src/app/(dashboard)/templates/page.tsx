'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '@/components/auth/auth-provider'
import { FolderCard } from '@/components/documents/folder-card'
import {
  createTemplateFolder,
  deleteTemplate,
  deleteTemplateFolder,
  getTemplateSignedUrl,
  listTemplateFolders,
  listTemplates,
  moveTemplateToFolder,
  renameTemplateFolder,
  updateTemplate,
  uploadTemplate,
  type TemplateFolderRow,
  type TemplateRow,
} from '@/lib/api'
import {
  ChevronRight,
  ExternalLink,
  FileText,
  FileType2,
  Loader2,
  Pencil,
  Plus,
  Search,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { CTA } from '@/components/ui/cta'

const ACCEPT = '.docx,.pdf,.txt,.md'
const FOLDER_UNFILED = '__unfiled__'
type FolderId = string

export default function TemplatesPage() {
  const { user } = useAuth()
  const [activeFolder, setActiveFolder] = useState<FolderId | null>(null)
  const [templates, setTemplates] = useState<TemplateRow[]>([])
  const [folders, setFolders] = useState<TemplateFolderRow[]>([])
  const [unfiledCount, setUnfiledCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [query, setQuery] = useState('')

  // Folder modals
  const [creatingFolder, setCreatingFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [renameTarget, setRenameTarget] = useState<TemplateFolderRow | null>(null)
  const [renameValue, setRenameValue] = useState('')

  // Template edit
  const [editing, setEditing] = useState<TemplateRow | null>(null)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')

  const [busyTemplate, setBusyTemplate] = useState<Record<string, boolean>>({})
  const fileInputRef = useRef<HTMLInputElement>(null)

  async function reload() {
    if (!user?.id) {
      setTemplates([])
      setFolders([])
      setUnfiledCount(0)
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const folderId =
        activeFolder === FOLDER_UNFILED ? 'unfiled' : activeFolder ?? null
      const [tplRes, folderRes] = await Promise.all([
        listTemplates(user.id, folderId ?? undefined),
        listTemplateFolders(user.id),
      ])
      setTemplates(tplRes.templates || [])
      setFolders(folderRes.folders)
      setUnfiledCount(folderRes.unfiled_count)
    } catch {
      setTemplates([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, activeFolder])

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file || !user?.id) return
    setUploading(true)
    try {
      const folderId =
        activeFolder && activeFolder !== FOLDER_UNFILED ? activeFolder : null
      await uploadTemplate(file, { userId: user.id, folderId })
      await reload()
    } catch (err) {
      console.error(err)
      alert('Upload failed. Templates must be .docx, .pdf, .txt or .md.')
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
      await createTemplateFolder(user.id, name)
      setNewFolderName('')
      setCreatingFolder(false)
      await reload()
    } catch {
      // collision: keep dialog open
    }
  }

  async function handleRenameFolder() {
    if (!renameTarget) return
    const name = renameValue.trim()
    if (!name) return
    try {
      await renameTemplateFolder(renameTarget.id, name)
      setRenameTarget(null)
      setRenameValue('')
      await reload()
    } catch {
      // ignore
    }
  }

  async function handleDeleteFolder(folder: TemplateFolderRow) {
    const ok = window.confirm(
      `Delete folder "${folder.name}"? Templates inside become unfiled. They are not deleted.`,
    )
    if (!ok) return
    try {
      await deleteTemplateFolder(folder.id, false)
      if (activeFolder === folder.id) setActiveFolder(null)
      await reload()
    } catch {
      // ignore
    }
  }

  async function handleSaveEdit() {
    if (!editing) return
    const name = editName.trim()
    if (!name) return
    try {
      await updateTemplate(editing.id, { name, description: editDescription.trim() })
      setEditing(null)
      await reload()
    } catch {
      // noop
    }
  }

  async function handleDelete(template: TemplateRow) {
    const ok = window.confirm(`Delete "${template.name}"? This cannot be undone.`)
    if (!ok) return
    try {
      await deleteTemplate(template.id)
      await reload()
    } catch {
      // noop
    }
  }

  async function handleOpen(template: TemplateRow) {
    try {
      const { signed_url } = await getTemplateSignedUrl(template.id)
      if (signed_url) window.open(signed_url, '_blank', 'noopener,noreferrer')
    } catch {
      // noop
    }
  }

  async function handleMove(template: TemplateRow, folderId: string | null) {
    setBusyTemplate((b) => ({ ...b, [template.id]: true }))
    try {
      await moveTemplateToFolder(template.id, folderId)
      await reload()
    } finally {
      setBusyTemplate((b) => ({ ...b, [template.id]: false }))
    }
  }

  const filtered = useMemo(() => {
    if (!query.trim()) return templates
    const q = query.toLowerCase()
    return templates.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        (t.description || '').toLowerCase().includes(q),
    )
  }, [templates, query])

  const activeFolderRow: TemplateFolderRow | null = useMemo(() => {
    if (!activeFolder || activeFolder === FOLDER_UNFILED) return null
    return folders.find((f) => f.id === activeFolder) ?? null
  }, [activeFolder, folders])

  const activeFolderTitle =
    activeFolder === FOLDER_UNFILED
      ? 'Unfiled'
      : activeFolderRow?.name ?? ''

  const isUserFolder = !!activeFolder && activeFolder !== FOLDER_UNFILED

  return (
    <div className="flex-1 overflow-y-auto" style={{ overscrollBehavior: 'none' }}>
      <div className="px-4 sm:px-6 py-6 max-w-5xl mx-auto w-full">
        <div className="flex items-start justify-between gap-3 mb-6">
          <div className="min-w-0">
            <h1
              className="text-3xl font-normal text-white/95 tracking-tight"
              style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
            >
              Templates
            </h1>
            <p className="text-[12.5px] text-white/40 mt-1 max-w-md leading-snug">
              {activeFolder
                ? 'Organise reusable skeletons. Levy can pick one when you ask it to draft.'
                : 'Save document skeletons you reuse. Levy can pick one when you ask it to draft.'}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT}
              onChange={handleUpload}
              className="hidden"
            />
            {activeFolder && (
              <>
                <CTA
                  size="md"
                  tone="primary"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading || !user}
                  iconOnly
                  startIcon={uploading ? <Loader2 className="animate-spin" /> : <Upload />}
                  aria-label={uploading ? 'Uploading' : 'Upload template'}
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

        {/* Breadcrumb */}
        {activeFolder && (
          <div className="flex items-center gap-1.5 mb-5 text-[12.5px] flex-wrap">
            <button
              onClick={() => setActiveFolder(null)}
              className="text-white/35 hover:text-emerald-400 transition-colors"
            >
              Templates
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

        {!user ? (
          <div className="py-16 text-center text-[13px] text-white/45">
            Sign in to save your templates.
          </div>
        ) : !activeFolder ? (
          /* Folder grid */
          <>
            {loading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="size-5 text-emerald-400 animate-spin" />
              </div>
            ) : (
              <div className="grid grid-cols-2 lg:grid-cols-3 gap-2.5 sm:gap-3 mb-8">
                {folders.map((f) => (
                  <FolderCard
                    key={f.id}
                    kind="user"
                    name={f.name}
                    count={f.doc_count}
                    onClick={() => setActiveFolder(f.id)}
                  />
                ))}
                {unfiledCount > 0 && (
                  <FolderCard
                    kind="user"
                    name="Unfiled"
                    count={unfiledCount}
                    onClick={() => setActiveFolder(FOLDER_UNFILED)}
                  />
                )}
                <FolderCard
                  kind="new"
                  name="New folder"
                  description="Group similar templates."
                  onClick={() => setCreatingFolder(true)}
                />
              </div>
            )}
            {folders.length === 0 && unfiledCount === 0 && !loading && (
              <EmptyState onUpload={() => fileInputRef.current?.click()} />
            )}
          </>
        ) : (
          /* Folder detail */
          <>
            <div className="relative max-w-sm mb-4">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/25" />
              <input
                type="text"
                placeholder="Filter templates"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.06] text-[12.5px] text-white/85 placeholder:text-white/20 focus:outline-none focus:border-emerald-500/30 transition-colors"
              />
            </div>

            {loading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="size-5 text-emerald-400 animate-spin" />
              </div>
            ) : filtered.length === 0 ? (
              <EmptyState onUpload={() => fileInputRef.current?.click()} />
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 sm:gap-3">
                {filtered.map((t) => (
                  <TemplateCard
                    key={t.id}
                    template={t}
                    folders={folders}
                    busy={!!busyTemplate[t.id]}
                    onOpen={() => handleOpen(t)}
                    onEdit={() => {
                      setEditing(t)
                      setEditName(t.name)
                      setEditDescription(t.description || '')
                    }}
                    onDelete={() => handleDelete(t)}
                    onMove={(folderId) => handleMove(t, folderId)}
                  />
                ))}
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

      {/* Edit template modal */}
      {editing && (
        <Modal onClose={() => setEditing(null)} title="Edit template">
          <label className="block text-[11px] uppercase tracking-wider text-white/35 mb-1">Name</label>
          <input
            autoFocus
            type="text"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            className="w-full px-3 py-2 rounded-lg bg-white/[0.04] border border-white/[0.08] text-[13px] text-white/85 focus:outline-none focus:border-emerald-500/40 mb-3"
          />
          <label className="block text-[11px] uppercase tracking-wider text-white/35 mb-1">Description</label>
          <textarea
            rows={3}
            value={editDescription}
            onChange={(e) => setEditDescription(e.target.value)}
            placeholder="Short description so Levy can match it to drafting requests."
            className="w-full px-3 py-2 rounded-lg bg-white/[0.04] border border-white/[0.08] text-[13px] text-white/85 placeholder:text-white/30 focus:outline-none focus:border-emerald-500/40 resize-none"
          />
          <div className="mt-3 flex justify-end gap-2">
            <button
              onClick={() => setEditing(null)}
              className="px-3 py-1.5 rounded-md text-[12px] text-white/55 hover:text-white/85"
            >
              Cancel
            </button>
            <button
              onClick={handleSaveEdit}
              disabled={!editName.trim()}
              className="px-3 py-1.5 rounded-md bg-emerald-500/15 border border-emerald-500/25 text-[12px] text-emerald-300 disabled:opacity-50"
            >
              Save
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function TemplateCard({
  template,
  folders,
  busy,
  onOpen,
  onEdit,
  onDelete,
  onMove,
}: {
  template: TemplateRow
  folders: TemplateFolderRow[]
  busy: boolean
  onOpen: () => void
  onEdit: () => void
  onDelete: () => void
  onMove: (folderId: string | null) => void
}) {
  const ext = template.file_type.toUpperCase()
  return (
    <div className="group relative rounded-xl border border-white/[0.06] bg-white/[0.02] hover:border-emerald-500/15 hover:bg-emerald-500/[0.02] transition-colors p-3.5">
      <button
        type="button"
        onClick={onOpen}
        className="flex items-start gap-3 w-full text-left"
      >
        <span className={`flex items-center justify-center size-10 rounded-lg flex-shrink-0 ${typeBadgeClass(template.file_type)}`}>
          {template.file_type === 'docx' ? (
            <FileType2 size={17} className="opacity-90" />
          ) : (
            <FileText size={17} className="opacity-90" />
          )}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-[13.5px] font-medium text-white/85 truncate">{template.name}</span>
            <ExternalLink className="size-3 text-white/20 group-hover:text-emerald-400/70 flex-shrink-0" />
          </div>
          <div className="flex items-center gap-1.5 mt-1 text-[10.5px] text-white/30">
            <span>{ext}</span>
            {template.page_count ? (
              <>
                <span className="text-white/15">·</span>
                <span>{template.page_count} page{template.page_count === 1 ? '' : 's'}</span>
              </>
            ) : null}
            {template.file_size_bytes ? (
              <>
                <span className="text-white/15">·</span>
                <span>{formatSize(template.file_size_bytes)}</span>
              </>
            ) : null}
          </div>
          {template.description && (
            <p className="text-[12px] text-white/45 leading-snug mt-1.5 line-clamp-2">
              {template.description}
            </p>
          )}
          {!template.description && template.preview_text && (
            <p className="text-[11.5px] text-white/30 leading-snug mt-1.5 line-clamp-2 italic">
              {template.preview_text.slice(0, 160)}
              {template.preview_text.length > 160 ? '...' : ''}
            </p>
          )}
        </div>
      </button>

      <div className="mt-3 flex items-center justify-between gap-2">
        {folders.length > 0 ? (
          <select
            value={template.folder_id ?? ''}
            onChange={(e) => onMove(e.target.value === '' ? null : e.target.value)}
            disabled={busy}
            className="px-2 py-1 rounded-md bg-white/[0.04] border border-white/[0.06] text-[11px] text-white/65 hover:border-white/[0.12] disabled:opacity-50 focus:outline-none focus:border-emerald-500/30"
          >
            <option value="">Unfiled</option>
            {folders.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        ) : <span />}
        <div className="flex items-center gap-1">
          <button
            onClick={onEdit}
            className="p-1.5 rounded hover:bg-white/[0.06] text-white/40 hover:text-white/70"
            aria-label="Edit"
          >
            <Pencil size={12} />
          </button>
          <button
            onClick={onDelete}
            className="p-1.5 rounded hover:bg-red-500/[0.08] text-white/40 hover:text-red-400"
            aria-label="Delete"
          >
            <Trash2 size={12} />
          </button>
        </div>
      </div>
    </div>
  )
}

function EmptyState({ onUpload }: { onUpload: () => void }) {
  return (
    <div className="py-16 text-center text-white/45">
      <Upload size={20} className="mx-auto mb-2.5 text-white/25" />
      <p className="text-[13px] text-white/65">No templates yet.</p>
      <p className="text-[11.5px] text-white/30 mt-1 max-w-sm mx-auto leading-snug">
        Drop in a .docx, .pdf, .txt, or .md you reuse. Offer letters, NDAs, demand letters all work.
      </p>
      <button
        onClick={onUpload}
        className="mt-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-emerald-500/12 border border-emerald-500/25 text-[12px] text-emerald-300 hover:bg-emerald-500/18"
      >
        <Plus size={12} /> Upload your first
      </button>
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
        className="relative w-full max-w-md rounded-xl border border-white/[0.08] bg-[#0d0d0f] p-4"
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

function typeBadgeClass(type: TemplateRow['file_type']): string {
  switch (type) {
    case 'docx':
      return 'bg-blue-500/10 border border-blue-500/20 text-blue-300'
    case 'pdf':
      return 'bg-red-500/10 border border-red-500/20 text-red-300'
    case 'md':
      return 'bg-purple-500/10 border border-purple-500/20 text-purple-300'
    case 'txt':
    default:
      return 'bg-white/[0.05] border border-white/[0.08] text-white/55'
  }
}

function formatSize(bytes?: number | null): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
