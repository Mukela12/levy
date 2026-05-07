'use client'

import { useState, useEffect, useRef } from 'react'
import { useAuth } from '@/components/auth/auth-provider'
import { getDocuments, uploadDocument } from '@/lib/api'
import { FileText, Loader2, Upload, Search, FolderOpen, ChevronRight, X } from 'lucide-react'
import type { DocumentInfo } from '@/lib/api'

interface FolderDef {
  name: string
  filter: (d: DocumentInfo) => boolean
}

const folders: FolderDef[] = [
  { name: 'Case Files', filter: (d: DocumentInfo) => d.title.includes('Contract') || d.title.includes('Client') },
  { name: 'Legislation', filter: (d: DocumentInfo) => d.title.includes('Act') || d.title.includes('Code') || d.title.includes('Constitution') },
  { name: 'Other Documents', filter: (_d: DocumentInfo) => true },
]

function FolderCard({ name, count, onClick }: { name: string; count: number; onClick: () => void }) {
  const [isHovered, setIsHovered] = useState(false)

  return (
    <div
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={onClick}
      className="p-5 rounded-2xl border border-white/[0.06] bg-white/[0.02] hover:border-emerald-500/20 cursor-pointer transition-all duration-300"
    >
      {/* 3D folder visual on desktop */}
      <div className="hidden md:flex items-center justify-center mb-4 h-28" style={{ perspective: '600px' }}>
        <div className="relative w-24 h-20" style={{ transformStyle: 'preserve-3d' }}>
          {/* Folder back */}
          <div
            className="absolute inset-0 rounded-lg bg-emerald-500/10 border border-emerald-500/15"
            style={{
              transform: 'rotateX(5deg)',
              transformOrigin: 'bottom center',
            }}
          />

          {/* Document cards fanning out */}
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="absolute left-3 right-3 h-12 rounded bg-white/[0.04] border border-white/[0.08]"
              style={{
                bottom: '8px',
                transform: isHovered
                  ? `translateY(${-20 - i * 14}px) rotateX(-2deg) rotateZ(${(i - 1) * 4}deg)`
                  : `translateY(${-2 - i * 2}px) rotateX(0deg) rotateZ(0deg)`,
                transition: `transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) ${i * 0.05}s`,
                transformOrigin: 'bottom center',
                zIndex: i,
              }}
            >
              <div className="p-1.5">
                <div className="h-1 w-8 rounded-full bg-white/[0.06]" />
                <div className="h-1 w-5 rounded-full bg-white/[0.04] mt-1" />
              </div>
            </div>
          ))}

          {/* Folder front flap */}
          <div
            className="absolute inset-x-0 bottom-0 h-14 rounded-lg rounded-tl-none bg-emerald-500/15 border border-emerald-500/20"
            style={{
              transform: isHovered ? 'rotateX(-35deg)' : 'rotateX(0deg)',
              transformOrigin: 'bottom center',
              transition: 'transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)',
              zIndex: 10,
            }}
          />

          {/* Folder tab */}
          <div
            className="absolute top-0 left-0 w-10 h-3 rounded-t-md bg-emerald-500/15 border border-emerald-500/20 border-b-0"
            style={{
              transform: isHovered ? 'translateY(-2px)' : 'translateY(0)',
              transition: 'transform 0.3s ease',
            }}
          />
        </div>
      </div>

      {/* Mobile: simple icon */}
      <div className="flex md:hidden items-center gap-3 mb-2">
        <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
          <FolderOpen size={18} className="text-emerald-400" />
        </div>
      </div>

      <h3 className="text-[14px] font-semibold text-white/80">{name}</h3>
      <p className="text-[12px] text-white/30 mt-0.5">{count} document{count !== 1 ? 's' : ''}</p>
    </div>
  )
}

function getFileIcon(title: string) {
  const isPdf = title.toLowerCase().includes('.pdf') || !title.toLowerCase().includes('.doc')
  return isPdf
    ? { bg: 'bg-red-500/10 border-red-500/20', text: 'text-red-400', label: 'PDF' }
    : { bg: 'bg-blue-500/10 border-blue-500/20', text: 'text-blue-400', label: 'DOCX' }
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [openFolder, setOpenFolder] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const { session } = useAuth()
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    loadDocuments()
  }, [])

  async function loadDocuments() {
    try {
      const res = await getDocuments(session?.access_token)
      setDocuments(res.details)
    } catch {
      try {
        const res = await getDocuments()
        setDocuments(res.details)
      } catch {
        setDocuments([])
      }
    } finally {
      setLoading(false)
    }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      await uploadDocument(file, session?.access_token)
      await loadDocuments()
    } catch {
      // upload failed silently
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const filteredDocuments = documents.filter((d) =>
    d.title.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const currentFolder = openFolder ? folders.find((f) => f.name === openFolder) : null
  const folderDocuments = currentFolder
    ? filteredDocuments.filter(currentFolder.filter)
    : filteredDocuments

  return (
    <div className="flex-1 overflow-y-auto" style={{ overscrollBehavior: 'none' }}>
      {/* Header */}
      <div className="px-6 py-6 flex items-center justify-between">
        <div>
          <h1
            className="text-2xl font-bold text-white/90"
            style={{ fontFamily: "'Playfair Display', serif" }}
          >
            Documents
          </h1>
          <p className="text-[12px] text-white/30 mt-1">
            Zambian legal documents indexed in the knowledge base
          </p>
        </div>
        <div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            onChange={handleUpload}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-[13px] font-medium text-emerald-400 hover:bg-emerald-500/15 transition-colors disabled:opacity-50"
          >
            {uploading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Upload size={14} />
            )}
            {uploading ? 'Uploading...' : 'Upload'}
          </button>
        </div>
      </div>

      <div className="px-6 pb-8">
        {/* Search */}
        <div className="relative max-w-md mb-6">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/20" />
          <input
            type="text"
            placeholder="Search documents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/[0.06] text-[13px] text-white/80 placeholder:text-white/20 focus:outline-none focus:border-emerald-500/30 transition-colors"
          />
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-6 h-6 text-emerald-400 animate-spin" />
          </div>
        ) : (
          <>
            {/* Breadcrumb when inside a folder */}
            {openFolder && (
              <div className="flex items-center gap-1.5 mb-5 text-[12px]">
                <button
                  onClick={() => setOpenFolder(null)}
                  className="text-white/30 hover:text-emerald-400 transition-colors"
                >
                  Documents
                </button>
                <ChevronRight size={10} className="text-white/15" />
                <span className="text-white/60">{openFolder}</span>
                <button
                  onClick={() => setOpenFolder(null)}
                  className="ml-2 p-0.5 rounded hover:bg-white/[0.05] text-white/20 hover:text-white/40 transition-colors"
                >
                  <X size={12} />
                </button>
              </div>
            )}

            {/* Folder grid (hidden when inside a folder) */}
            {!openFolder && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-8">
                {folders.map((folder) => {
                  const count = filteredDocuments.filter(folder.filter).length
                  return (
                    <FolderCard
                      key={folder.name}
                      name={folder.name}
                      count={count}
                      onClick={() => setOpenFolder(folder.name)}
                    />
                  )
                })}
              </div>
            )}

            {/* Document table */}
            <div>
              <h2 className="text-[11px] uppercase tracking-widest text-white/25 font-semibold mb-3">
                {openFolder ? openFolder : 'All Documents'}
              </h2>

              {folderDocuments.length === 0 ? (
                <p className="text-[13px] text-white/30 py-8 text-center">No documents found.</p>
              ) : (
                <div className="space-y-2">
                  {folderDocuments.map((doc, i) => {
                    const fileStyle = getFileIcon(doc.title)
                    return (
                      <div
                        key={i}
                        className="flex items-center gap-4 p-4 rounded-xl border border-white/[0.06] bg-white/[0.02] hover:border-white/[0.1] transition-colors"
                      >
                        <div
                          className={`w-10 h-10 rounded-lg ${fileStyle.bg} border flex items-center justify-center flex-shrink-0`}
                        >
                          <FileText size={16} className={fileStyle.text} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-[13px] font-medium text-white/80 truncate">
                            {doc.title}
                          </p>
                          <p className="text-[11px] text-white/25 mt-0.5">
                            {doc.year ? `${doc.year}` : 'N/A'} &middot; {doc.total_sections} sections &middot; {doc.total_chunks} chunks
                          </p>
                        </div>
                        <span className="text-[10px] px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 font-medium flex-shrink-0 border border-emerald-500/15">
                          Indexed
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
