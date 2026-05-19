'use client'

import { useEffect, useRef, useState } from 'react'
import { motion, useDragControls, type PanInfo } from 'framer-motion'
import { Loader2, ChevronLeft, ChevronRight, X, ExternalLink, Maximize2, Minimize2 } from 'lucide-react'

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

// Snap points for the mobile bottom-sheet, expressed as % of viewport height
// the sheet covers. Bigger = more visible.
const SNAP_FULL = 0.92
const SNAP_MID = 0.55
const SNAP_PEEK = 0.16
const DISMISS_VELOCITY = 700  // px/s - flick faster than this dismisses
const DISMISS_DRAG_PX = 120   // dragging down >120px past peek dismisses

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
        // Artifact path takes precedence - those are agent-generated PDFs.
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

      const cssWidth = Math.max(280, Math.min(container.clientWidth, 900) - 24)
      const baseViewport = page.getViewport({ scale: 1 })
      const scale = cssWidth / baseViewport.width
      const viewport = page.getViewport({ scale })
      const dpr = window.devicePixelRatio || 1

      const canvas = document.createElement('canvas')
      canvas.width = Math.floor(viewport.width * dpr)
      canvas.height = Math.floor(viewport.height * dpr)
      canvas.style.width = `${viewport.width}px`
      canvas.style.height = `${viewport.height}px`
      canvas.className = 'rounded-md shadow-[0_8px_32px_-12px_rgba(0,0,0,0.6)]'
      const ctx = canvas.getContext('2d')
      if (!ctx) return

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

  const titleText = meta?.short_name || meta?.title || citation.actName

  // Shared body - used by both desktop and mobile shells.
  const Body = (
    <>
      <div className="flex items-center justify-between gap-3 px-4 py-2 border-b border-white/[0.06] bg-white/[0.015] flex-shrink-0">
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

      <div className="flex-1 overflow-auto bg-[#06060a] flex items-start justify-center min-h-0">
        {loading && (
          <div className="flex items-center gap-2 text-[12px] text-white/40 py-12">
            <Loader2 className="size-4 animate-spin" /> loading PDF…
          </div>
        )}
        {error && (
          <div className="max-w-md py-12 px-6 text-center">
            <p className="text-[13px] text-amber-400/85 mb-1">This PDF couldn't be rendered.</p>
            <p className="text-[11.5px] text-white/45 leading-relaxed mb-3">
              Some scanned or password-protected files don't render in-browser. You can still download the original.
            </p>
            {meta?.signed_url && (
              <a
                href={meta.signed_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[11.5px] bg-emerald-500/10 border border-emerald-500/25 text-emerald-300 hover:bg-emerald-500/15"
              >
                Open in new tab
              </a>
            )}
            <p className="text-[10.5px] text-white/25 mt-4 break-all">{error}</p>
          </div>
        )}
        {!loading && !error && (
          <div ref={containerRef} className="w-full flex justify-center py-3 px-3" />
        )}
      </div>
    </>
  )

  return (
    <>
      {/* ── Desktop: right-side aside ── */}
      <aside
        className="hidden md:flex fixed inset-y-0 right-0 z-40 w-full max-w-[640px] flex-col border-l border-white/[0.06] bg-[#0a0a0b] shadow-[0_0_60px_-10px_rgba(0,0,0,0.5)]"
        style={{ pointerEvents: 'auto' }}
        aria-label="PDF source viewer"
      >
        <header className="flex items-start gap-3 px-4 py-3 border-b border-white/[0.06] flex-shrink-0">
          <div className="flex-1 min-w-0">
            <div className="text-[12px] font-bold tracking-[0.2em] uppercase text-emerald-400">
              Source
            </div>
            <div className="text-[14px] font-semibold text-white/85 truncate mt-0.5">{titleText}</div>
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
              title="Open original"
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
        {Body}
      </aside>

      {/* ── Mobile: draggable bottom-sheet ── */}
      <PdfMobileSheet
        title={titleText}
        subtitle={headerSubtitle}
        canonicalUrl={meta?.canonical_url}
        onClose={onClose}
      >
        {Body}
      </PdfMobileSheet>
    </>
  )
}

/**
 * Mobile-only bottom-sheet with three snap points (peek / mid / full) plus
 * flick-to-dismiss. Header has a drag handle and a maximise button so users
 * who don't intuit the gesture can still expand.
 *
 * Why three points: peek lets the chat behind stay readable while the user
 * remembers the source is open; mid is the comfortable default; full is the
 * "I want to read this" mode.
 */
function PdfMobileSheet({
  title,
  subtitle,
  canonicalUrl,
  onClose,
  children,
}: {
  title: string
  subtitle?: string
  canonicalUrl?: string
  onClose: () => void
  children: React.ReactNode
}) {
  type Snap = 'peek' | 'mid' | 'full'
  const [snap, setSnap] = useState<Snap>('mid')
  const [vh, setVh] = useState(800)
  const dragControls = useDragControls()

  // Track viewport height for snap math
  useEffect(() => {
    const onResize = () => setVh(window.innerHeight || 800)
    onResize()
    window.addEventListener('resize', onResize)
    window.addEventListener('orientationchange', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      window.removeEventListener('orientationchange', onResize)
    }
  }, [])

  // y-offset measured from the FULL-sized sheet's top. Larger y = sheet sits
  // lower on the screen (less visible). y=0 = full.
  const fullHeight = vh * SNAP_FULL
  const yForMid = fullHeight - vh * SNAP_MID
  const yForPeek = fullHeight - vh * SNAP_PEEK

  const yForSnap = (s: Snap): number =>
    s === 'full' ? 0 : s === 'mid' ? yForMid : yForPeek

  function handleDragEnd(_: unknown, info: PanInfo) {
    const newY = yForSnap(snap) + info.offset.y
    const v = info.velocity.y

    // Flick-to-dismiss from any state when velocity is high & downward
    if (v > DISMISS_VELOCITY) {
      onClose()
      return
    }
    // Past peek + extra drag = dismiss
    if (newY > yForPeek + DISMISS_DRAG_PX) {
      onClose()
      return
    }

    // Snap to nearest of full / mid / peek
    const candidates: Snap[] = ['full', 'mid', 'peek']
    let best: Snap = snap
    let bestDist = Infinity
    for (const c of candidates) {
      const d = Math.abs(newY - yForSnap(c))
      if (d < bestDist) {
        best = c
        bestDist = d
      }
    }
    setSnap(best)
  }

  return (
    <motion.aside
      drag="y"
      dragControls={dragControls}
      dragListener={false}
      dragConstraints={{ top: 0, bottom: yForPeek + DISMISS_DRAG_PX + 60 }}
      dragElastic={0.05}
      dragMomentum={false}
      onDragEnd={handleDragEnd}
      initial={{ y: vh }}
      animate={{ y: yForSnap(snap) }}
      exit={{ y: vh, transition: { duration: 0.2 } }}
      transition={{ type: 'spring', stiffness: 360, damping: 38 }}
      style={{ height: fullHeight }}
      className="md:hidden fixed left-0 right-0 bottom-0 z-40 bg-[#0a0a0b] border-t border-white/[0.06] rounded-t-2xl shadow-[0_-12px_40px_-10px_rgba(0,0,0,0.6)] flex flex-col"
      aria-label="PDF source viewer"
    >
      {/* Drag handle row - only the handle and header initiate drag, so the
          PDF body remains independently scrollable. */}
      <div
        className="flex items-center justify-center pt-2 pb-1 cursor-grab active:cursor-grabbing"
        style={{ touchAction: 'none' }}
        onPointerDown={(e) => dragControls.start(e)}
        onClick={() => setSnap(snap === 'full' ? 'mid' : 'full')}
      >
        <div className="h-1 w-10 rounded-full bg-white/20" />
      </div>

      {/* Header - also a drag region so users can pull from the title area */}
      <header
        className="flex items-start gap-3 px-4 py-2 pb-3 border-b border-white/[0.06] flex-shrink-0"
        style={{ touchAction: 'none' }}
        onPointerDown={(e) => {
          // Only start drag from the non-button part of the header
          const target = e.target as HTMLElement
          if (target.closest('button, a, input')) return
          dragControls.start(e)
        }}
      >
        <div className="flex-1 min-w-0">
          <div className="text-[10.5px] font-bold tracking-[0.2em] uppercase text-emerald-400">
            Source
          </div>
          <div className="text-[14px] font-semibold text-white/85 truncate mt-0.5">{title}</div>
          {subtitle && <div className="text-[11px] text-white/35 mt-0.5">{subtitle}</div>}
        </div>
        {canonicalUrl && (
          <a
            href={canonicalUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-white/30 hover:text-white/60 transition-colors p-1.5"
            aria-label="Open original on the source site"
          >
            <ExternalLink className="w-4 h-4" />
          </a>
        )}
        <button
          type="button"
          onClick={() => setSnap(snap === 'full' ? 'peek' : 'full')}
          className="text-white/30 hover:text-white/60 transition-colors p-1.5"
          aria-label={snap === 'full' ? 'Minimise viewer' : 'Maximise viewer'}
        >
          {snap === 'full' ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
        </button>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close source viewer"
          className="text-white/30 hover:text-white/60 transition-colors p-1.5"
        >
          <X className="w-4 h-4" />
        </button>
      </header>

      {/* Body - hidden when peeking so a tiny height doesn't render a useless
          page-nav strip. Tapping the handle pops back to full. */}
      <div className={`flex flex-col flex-1 min-h-0 ${snap === 'peek' ? 'opacity-30 pointer-events-none' : ''}`}>
        {children}
      </div>
    </motion.aside>
  )
}
