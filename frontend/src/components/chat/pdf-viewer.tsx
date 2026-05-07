'use client'

import { useEffect, useRef, useState } from 'react'
import { Loader2, ChevronLeft, ChevronRight, X, ExternalLink } from 'lucide-react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || ''

interface PdfDocMeta {
  document_id: string
  title?: string
  short_name?: string
  page_count?: number
  canonical_url?: string
  signed_url: string
}

export interface PdfViewerCitation {
  // Either a corpus document or an artifact:
  documentId?: string
  artifactId?: string
  actName: string
  pageStart?: number
  pageEnd?: number
  section?: string
}

interface PdfViewerProps {
  citation: PdfViewerCitation | null
  onClose: () => void
}

export function PdfViewer({ citation, onClose }: PdfViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [meta, setMeta] = useState<PdfDocMeta | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pageNum, setPageNum] = useState<number>(1)
  const [pageCount, setPageCount] = useState<number>(1)

  // Reset state when citation changes (or panel closes).
  useEffect(() => {
    setMeta(null)
    setError(null)
    setPageNum(citation?.pageStart ?? 1)
  }, [citation?.documentId, citation?.actName, citation?.pageStart])

  // Resolve document/artifact → signed URL.
  useEffect(() => {
    if (!citation) return
    let cancelled = false
    setLoading(true)
    ;(async () => {
      try {
        // Artifact path takes precedence — those are agent-generated PDFs.
        if (citation.artifactId) {
          const r = await fetch(`${API_URL}/api/artifacts/${citation.artifactId}/pdf`)
          if (!r.ok) throw new Error((await r.text()) || `artifact ${r.status}`)
          const j = (await r.json()) as PdfDocMeta & { kind?: string }
          if (cancelled) return
          setMeta(j)
          setPageCount(j.page_count || 1)
          return
        }

        let documentId = citation.documentId
        if (!documentId) {
          // Fallback: look up by act name (older citation snapshots).
          const r = await fetch(
            `${API_URL}/api/documents/by-title?title=${encodeURIComponent(citation.actName)}`,
          )
          if (!r.ok) throw new Error(`title lookup ${r.status}`)
          const j = await r.json()
          documentId = j.matches?.[0]?.id
          if (!documentId) throw new Error('no matching document')
        }
        const r = await fetch(`${API_URL}/api/documents/${documentId}/pdf`)
        if (!r.ok) {
          const text = await r.text()
          throw new Error(text || `pdf url ${r.status}`)
        }
        const j = (await r.json()) as PdfDocMeta
        if (cancelled) return
        setMeta(j)
        setPageCount(j.page_count || 1)
      } catch (e) {
        if (!cancelled) setError(String((e as Error).message || e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [citation])

  // Render with pdfjs once we have the URL.
  useEffect(() => {
    if (!meta || !containerRef.current) return
    let cancelled = false

    ;(async () => {
      const pdfjs = await import('pdfjs-dist')
      // Worker is shipped as a public asset path — we vendor it via next.config
      // public dir below.
      ;(pdfjs as unknown as { GlobalWorkerOptions: { workerSrc: string } }).GlobalWorkerOptions.workerSrc =
        '/pdf.worker.min.mjs'

      const loadingTask = pdfjs.getDocument({ url: meta.signed_url })
      const doc = await loadingTask.promise
      if (cancelled) return
      setPageCount(doc.numPages)

      const target = Math.min(Math.max(1, pageNum), doc.numPages)
      const page = await doc.getPage(target)
      const container = containerRef.current
      if (!container || cancelled) return

      const cssWidth = Math.max(320, Math.min(container.clientWidth, 900) - 24)
      const baseViewport = page.getViewport({ scale: 1 })
      const scale = cssWidth / baseViewport.width
      const viewport = page.getViewport({ scale })
      const dpr = window.devicePixelRatio || 1

      // Recommended pdfjs render path: use the `transform` option for DPI
      // scaling so we don't have to call ctx.scale ourselves.
      const canvas = document.createElement('canvas')
      canvas.width = Math.floor(viewport.width * dpr)
      canvas.height = Math.floor(viewport.height * dpr)
      canvas.style.width = `${viewport.width}px`
      canvas.style.height = `${viewport.height}px`
      canvas.className = 'rounded-md shadow-[0_8px_32px_-12px_rgba(0,0,0,0.6)]'
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      // Replace previous render synchronously, then start the new one.
      container.replaceChildren(canvas)

      const transform = dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined
      await page.render({
        canvasContext: ctx,
        viewport,
        ...(transform ? { transform } : {}),
      } as Parameters<typeof page.render>[0]).promise
    })().catch((e) => {
      if (!cancelled) setError(String((e as Error).message || e))
    })

    return () => {
      cancelled = true
    }
  }, [meta, pageNum])

  if (!citation) return null

  const headerSubtitle = [
    citation.section ? `S.${citation.section}` : null,
    citation.pageStart ? `p.${citation.pageStart}` : null,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <aside
      className="fixed inset-y-0 right-0 z-40 w-full max-w-[640px] flex flex-col border-l border-white/[0.06] bg-[#0a0a0b] shadow-[0_0_60px_-10px_rgba(0,0,0,0.5)]"
      style={{ pointerEvents: 'auto' }}
      aria-label="PDF source viewer"
    >
      {/* Header */}
      <header className="flex items-start gap-3 px-4 py-3 border-b border-white/[0.06]">
        <div className="flex-1 min-w-0">
          <div className="text-[12px] font-bold tracking-[0.2em] uppercase text-emerald-400">
            Source
          </div>
          <div className="text-[14px] font-semibold text-white/85 truncate mt-0.5">
            {meta?.short_name || meta?.title || citation.actName}
          </div>
          {headerSubtitle && (
            <div className="text-[11px] text-white/35 mt-0.5">{headerSubtitle}</div>
          )}
        </div>
        {meta?.canonical_url && (
          <a
            href={meta.canonical_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-white/30 hover:text-white/60 transition-colors p-1.5"
            title="Open original on the source site"
            aria-label="Open original on the source site"
          >
            <ExternalLink className="w-4 h-4" />
          </a>
        )}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close source viewer"
          className="text-white/30 hover:text-white/60 transition-colors p-1.5"
        >
          <X className="w-4 h-4" />
        </button>
      </header>

      {/* Page nav */}
      <div className="flex items-center justify-between gap-3 px-4 py-2 border-b border-white/[0.06] bg-white/[0.015]">
        <button
          type="button"
          onClick={() => setPageNum((p) => Math.max(1, p - 1))}
          disabled={pageNum <= 1 || !meta}
          className="size-8 rounded-md border border-white/[0.06] flex items-center justify-center text-white/60 disabled:opacity-30 hover:bg-white/[0.04]"
          aria-label="Previous page"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <div className="flex items-center gap-2 text-[12px] text-white/55">
          <span>Page</span>
          <input
            type="number"
            min={1}
            max={pageCount}
            value={pageNum}
            onChange={(e) => {
              const n = Number(e.target.value)
              if (Number.isFinite(n)) setPageNum(Math.min(Math.max(1, n), pageCount))
            }}
            className="w-14 h-7 rounded-md bg-white/[0.04] border border-white/[0.06] text-center text-white/85 focus:outline-none focus:border-emerald-500/30"
          />
          <span className="text-white/30">/ {pageCount}</span>
        </div>
        <button
          type="button"
          onClick={() => setPageNum((p) => Math.min(pageCount, p + 1))}
          disabled={pageNum >= pageCount || !meta}
          className="size-8 rounded-md border border-white/[0.06] flex items-center justify-center text-white/60 disabled:opacity-30 hover:bg-white/[0.04]"
          aria-label="Next page"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto bg-[#06060a] flex items-start justify-center">
        {loading && (
          <div className="flex items-center gap-2 text-[12px] text-white/40 py-12">
            <Loader2 className="size-4 animate-spin" /> loading PDF…
          </div>
        )}
        {error && (
          <div className="text-[12.5px] text-amber-400/80 max-w-md py-12 px-6">
            {error}
          </div>
        )}
        {!loading && !error && (
          <div ref={containerRef} className="w-full flex justify-center py-3 px-3" />
        )}
      </div>
    </aside>
  )
}
