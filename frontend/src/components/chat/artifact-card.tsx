'use client'

import { useState } from 'react'
import { FileText, Download, Loader2, Layers, Scissors, Globe } from 'lucide-react'
import { LevyLogo } from '@/components/ui/levy-logo'
import type { ArtifactView } from '@/lib/api'

const API_URL = process.env.NEXT_PUBLIC_API_URL || ''

interface ArtifactCardProps {
  artifact: ArtifactView
  onOpen?: () => void
}

// For agent-generated PDFs we show the Levy mark instead of a Lucide icon —
// hence the slightly odd union type. The Icon is rendered with className,
// LevyLogo with size, so we branch at the render site.
const SOURCE_META: Record<
  string,
  { label: string; Icon: typeof FileText | null }
> = {
  generated: { label: 'Generated', Icon: null },
  extracted: { label: 'Extracted', Icon: Scissors },
  merged: { label: 'Merged', Icon: Layers },
  uploaded: { label: 'Uploaded', Icon: FileText },
  fetched: { label: 'From the web', Icon: Globe },
}

function formatBytes(n?: number): string {
  if (!n) return ''
  if (n < 1024) return `${n}B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)}KB`
  return `${(n / (1024 * 1024)).toFixed(1)}MB`
}

export function ArtifactCard({ artifact, onOpen }: ArtifactCardProps) {
  const [downloading, setDownloading] = useState(false)
  const meta = SOURCE_META[artifact.source] ?? SOURCE_META.uploaded
  const Icon = meta.Icon
  const sizeLabel = formatBytes(artifact.size_bytes)
  const pageLabel =
    typeof artifact.page_count === 'number' ? `${artifact.page_count} page${artifact.page_count === 1 ? '' : 's'}` : null

  async function handleDownload() {
    if (downloading) return
    setDownloading(true)
    try {
      const r = await fetch(`${API_URL}/api/artifacts/${artifact.id}/pdf`)
      if (!r.ok) throw new Error(`download ${r.status}`)
      const j = await r.json()
      const a = document.createElement('a')
      a.href = j.signed_url
      a.download = `${artifact.title}.pdf`
      a.target = '_blank'
      a.rel = 'noopener noreferrer'
      document.body.appendChild(a)
      a.click()
      a.remove()
    } catch {
      // best-effort; user can retry
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{
        background:
          'linear-gradient(180deg, rgba(34, 197, 94, 0.06) 0%, rgba(34, 197, 94, 0.02) 100%)',
        border: '1px solid rgba(34, 197, 94, 0.18)',
        boxShadow: '0 8px 28px -12px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.04)',
      }}
    >
      <button
        type="button"
        onClick={onOpen}
        className="w-full text-left px-4 py-3.5 flex items-center gap-3 hover:bg-emerald-500/[0.04] transition-colors"
      >
        <span className="flex items-center justify-center size-10 rounded-lg bg-emerald-500/15 border border-emerald-500/25 text-emerald-400 flex-shrink-0">
          <FileText className="size-5" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 text-[10px] font-medium tracking-[0.16em] uppercase text-emerald-400/80">
            {Icon ? <Icon className="size-3" /> : <LevyLogo size={12} />}
            <span>{meta.label} PDF</span>
          </div>
          <div className="text-[14px] font-semibold text-white/85 mt-0.5 truncate">
            {artifact.title}
          </div>
          <div className="text-[11px] text-white/35 mt-0.5">
            {[pageLabel, sizeLabel].filter(Boolean).join(' · ')}
          </div>
        </div>
      </button>
      <div className="border-t border-emerald-500/10 px-4 py-2 flex items-center gap-2 bg-black/20">
        <button
          type="button"
          onClick={onOpen}
          className="flex-1 text-[12px] text-emerald-400/80 hover:text-emerald-400 text-left transition-colors"
        >
          Open in viewer →
        </button>
        <button
          type="button"
          onClick={handleDownload}
          disabled={downloading}
          className="flex items-center gap-1.5 text-[11px] text-white/40 hover:text-white/70 transition-colors disabled:opacity-50"
          aria-label="Download artifact"
        >
          {downloading ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Download className="size-3.5" />
          )}
          <span>Download</span>
        </button>
      </div>
    </div>
  )
}
