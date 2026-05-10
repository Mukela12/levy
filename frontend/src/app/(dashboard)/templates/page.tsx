'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '@/components/auth/auth-provider'
import {
  deleteTemplate,
  getTemplateSignedUrl,
  listTemplates,
  updateTemplate,
  uploadTemplate,
  type TemplateRow,
} from '@/lib/api'
import {
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

const ACCEPT = '.docx,.pdf,.txt,.md'

export default function TemplatesPage() {
  const { user } = useAuth()
  const [templates, setTemplates] = useState<TemplateRow[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<TemplateRow | null>(null)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  async function reload() {
    if (!user?.id) {
      setTemplates([])
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const data = await listTemplates(user.id)
      setTemplates(data.templates || [])
    } catch {
      setTemplates([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id])

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file || !user?.id) return
    setUploading(true)
    try {
      await uploadTemplate(file, { userId: user.id })
      await reload()
    } catch (err) {
      console.error(err)
      alert('Upload failed. Templates must be .docx, .pdf, .txt or .md.')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
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
    const ok = window.confirm(`Delete template "${template.name}"? This cannot be undone.`)
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

  const filtered = useMemo(() => {
    if (!query.trim()) return templates
    const q = query.toLowerCase()
    return templates.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        (t.description || '').toLowerCase().includes(q),
    )
  }, [templates, query])

  return (
    <div className="flex-1 overflow-y-auto" style={{ overscrollBehavior: 'none' }}>
      <div className="px-6 py-6 max-w-5xl mx-auto w-full">
        <div className="flex items-start justify-between gap-3 mb-6">
          <div>
            <h1
              className="text-2xl font-bold text-white/90 tracking-tight"
              style={{ fontFamily: "'Playfair Display', serif" }}
            >
              Templates
            </h1>
            <p className="text-[12px] text-white/35 mt-1 max-w-xl">
              Reusable document skeletons (.docx, .pdf, .txt, .md). Levy can
              suggest one of these when you ask it to draft a new document.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT}
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
              <span>{uploading ? 'Uploading…' : 'Upload template'}</span>
            </button>
          </div>
        </div>

        {!user ? (
          <div className="py-16 text-center text-[13px] text-white/45">
            Sign in to save and reuse templates across your consultations.
          </div>
        ) : loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="size-5 text-emerald-400 animate-spin" />
          </div>
        ) : templates.length === 0 ? (
          <EmptyState onUpload={() => fileInputRef.current?.click()} />
        ) : (
          <>
            <div className="relative max-w-sm mb-4">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/25" />
              <input
                type="text"
                placeholder="Filter templates…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.06] text-[12.5px] text-white/85 placeholder:text-white/20 focus:outline-none focus:border-emerald-500/30 transition-colors"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 sm:gap-3">
              {filtered.map((t) => (
                <TemplateCard
                  key={t.id}
                  template={t}
                  onOpen={() => handleOpen(t)}
                  onEdit={() => {
                    setEditing(t)
                    setEditName(t.name)
                    setEditDescription(t.description || '')
                  }}
                  onDelete={() => handleDelete(t)}
                />
              ))}
            </div>
          </>
        )}
      </div>

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
  onOpen,
  onEdit,
  onDelete,
}: {
  template: TemplateRow
  onOpen: () => void
  onEdit: () => void
  onDelete: () => void
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
              {template.preview_text.length > 160 ? '…' : ''}
            </p>
          )}
        </div>
      </button>

      <div className="absolute top-2 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={onEdit}
          className="p-1 rounded hover:bg-white/[0.06] text-white/40 hover:text-white/70"
          aria-label="Edit"
        >
          <Pencil size={12} />
        </button>
        <button
          onClick={onDelete}
          className="p-1 rounded hover:bg-red-500/[0.08] text-white/40 hover:text-red-400"
          aria-label="Delete"
        >
          <Trash2 size={12} />
        </button>
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
        Upload a .docx, .pdf, .txt, or .md skeleton — an offer letter, NDA, demand letter,
        whatever you reuse. Levy can suggest matching templates when you ask it to draft.
      </p>
      <button
        onClick={onUpload}
        className="mt-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-emerald-500/12 border border-emerald-500/25 text-[12px] text-emerald-300 hover:bg-emerald-500/18"
      >
        <Plus size={12} /> Upload your first template
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
