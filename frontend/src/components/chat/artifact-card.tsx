'use client'

import { useEffect, useState } from 'react'
import { FileText, Download, Loader2, Layers, Scissors, Globe, Copy, Check, ChevronDown } from 'lucide-react'
import { LevyLogo } from '@/components/ui/levy-logo'
import { authHeaders, type ArtifactView } from '@/lib/api'

const API_URL = process.env.NEXT_PUBLIC_API_URL || ''

/** Ask Supabase Storage to serve the file as an attachment, not inline. */
function withDownloadParam(url: string, filename: string): string {
  try {
    const u = new URL(url)
    u.searchParams.set('download', filename)
    return u.toString()
  } catch {
    return url
  }
}


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
  const [busy, setBusy] = useState<null | 'pdf' | 'docx'>(null)
  const [copied, setCopied] = useState(false)
  const [showText, setShowText] = useState(false)
  const [text, setText] = useState<string | null>(null)
  const [textState, setTextState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [downloadFailed, setDownloadFailed] = useState(false)
  const meta = SOURCE_META[artifact.source] ?? SOURCE_META.uploaded
  const Icon = meta.Icon
  const sizeLabel = formatBytes(artifact.size_bytes)
  const pageLabel =
    typeof artifact.page_count === 'number' ? `${artifact.page_count} page${artifact.page_count === 1 ? '' : 's'}` : null
  // Only Levy-generated documents carry editable source, so only they can be
  // exported to Word. Uploaded / extracted / merged / fetched PDFs cannot.
  const canWord = artifact.source === 'generated'
  // When the PDF render failed, the document was still saved as text. Lead with
  // it: no PDF to download, so auto-open the text and hide the PDF button.
  const pdfFailed = (artifact.meta as { pdf_failed?: boolean } | undefined)?.pdf_failed === true

  useEffect(() => {
    if (pdfFailed) {
      setShowText(true)
      void ensureText()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pdfFailed])

  async function handleDownload(fmt: 'pdf' | 'docx') {
    if (busy) return
    setBusy(fmt)
    try {
      // MUST send the bearer token. These artifacts are owner-scoped, so an
      // unauthenticated GET is a 403 — which is exactly what shipped: every
      // Download on a signed-in user's own document failed, silently. It
      // survived testing because anonymous-demo artifacts have owner_id NULL
      // and are served by capability, so the logged-out path looked fine.
      const r = await fetch(`${API_URL}/api/artifacts/${artifact.id}/${fmt}`, {
        headers: await authHeaders(),
      })
      if (!r.ok) throw new Error(`download ${r.status}`)
      const j = await r.json()
      const a = document.createElement('a')
      // `a.download` is ignored on cross-origin URLs, so on mobile (most of
      // Levy's traffic) the file would just open in a tab. Supabase honours a
      // `download` query param by setting Content-Disposition: attachment,
      // which makes it a real save on both mobile and desktop.
      a.href = withDownloadParam(j.signed_url, `${artifact.title}.${fmt}`)
      a.download = `${artifact.title}.${fmt}`
      a.target = '_blank'
      a.rel = 'noopener noreferrer'
      document.body.appendChild(a)
      a.click()
      a.remove()
    } catch {
      // A dead button that reports nothing is worse than an error: the user
      // who hit this clicked Download, saw nothing happen, and left for
      // ChatGPT mid-emergency. Say something and offer the text instead.
      setDownloadFailed(true)
      setShowText(true)
      void ensureText()
    } finally {
      setBusy(null)
    }
  }

  // Fetch the plain text once and cache it. Mobile downloads of signed PDF URLs
  // are unreliable and users asked to "just type the reply into copyable text",
  // so reading/copying the text straight from the card is the dependable path.
  async function ensureText(): Promise<string | null> {
    if (text !== null) return text
    setTextState('loading')
    try {
      const r = await fetch(`${API_URL}/api/artifacts/${artifact.id}/text`, {
        headers: await authHeaders(),
      })
      if (!r.ok) throw new Error(`text ${r.status}`)
      const j = await r.json()
      const t = (j.text as string) || ''
      setText(t)
      setTextState('idle')
      return t
    } catch {
      setTextState('error')
      return null
    }
  }

  async function handleCopy() {
    const t = await ensureText()
    if (t === null) return
    try {
      await navigator.clipboard.writeText(t)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // clipboard blocked; the text is still visible in the panel to select
    }
  }

  async function handleToggleText() {
    const next = !showText
    setShowText(next)
    if (next) await ensureText()
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
        onClick={pdfFailed ? handleToggleText : onOpen}
        className="w-full text-left px-4 py-3.5 flex items-center gap-3 hover:bg-emerald-500/[0.04] transition-colors"
      >
        <span className="flex items-center justify-center size-10 rounded-lg bg-emerald-500/15 border border-emerald-500/25 text-emerald-400 flex-shrink-0">
          <FileText className="size-5" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 text-[10px] font-medium tracking-[0.16em] uppercase text-emerald-400/80">
            {Icon ? <Icon className="size-3" /> : <LevyLogo size={12} />}
            <span>{pdfFailed ? `${meta.label} · text` : `${meta.label} PDF`}</span>
          </div>
          <div className="text-[14px] font-semibold text-white/85 mt-0.5 truncate">
            {artifact.title}
          </div>
          <div className="text-[11px] text-white/35 mt-0.5">
            {[pageLabel, sizeLabel].filter(Boolean).join(' · ')}
          </div>
        </div>
      </button>
      <div className="border-t border-emerald-500/10 px-4 py-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 bg-black/20">
        {canWord && (
          <button
            type="button"
            onClick={handleToggleText}
            aria-expanded={showText}
            className="flex items-center gap-1.5 text-[11px] text-emerald-400/85 hover:text-emerald-400 transition-colors"
          >
            <ChevronDown className={`size-3.5 transition-transform ${showText ? 'rotate-180' : ''}`} />
            <span>{showText ? 'Hide text' : 'View text'}</span>
          </button>
        )}
        {pdfFailed ? (
          <span className="flex-1 min-w-[70px] text-[12px] text-amber-300/70">
            PDF unavailable, text below
          </span>
        ) : (
          <button
            type="button"
            onClick={onOpen}
            className="flex-1 min-w-[70px] text-[12px] text-white/40 hover:text-white/70 text-left transition-colors"
          >
            Open in viewer →
          </button>
        )}
        {!pdfFailed && (
          <button
            type="button"
            onClick={() => handleDownload('pdf')}
            disabled={busy !== null}
            className="flex items-center gap-1.5 text-[11px] text-white/40 hover:text-white/70 transition-colors disabled:opacity-50"
            aria-label="Download PDF"
          >
            {busy === 'pdf' ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
            <span>PDF</span>
          </button>
        )}
        {canWord && (
          <button
            type="button"
            data-testid="artifact-word"
            onClick={() => handleDownload('docx')}
            disabled={busy !== null}
            className="flex items-center gap-1.5 text-[11px] text-white/40 hover:text-white/70 transition-colors disabled:opacity-50"
            aria-label="Download Word document"
          >
            {busy === 'docx' ? <Loader2 className="size-3.5 animate-spin" /> : <FileText className="size-3.5" />}
            <span>Word</span>
          </button>
        )}
        {canWord && (
          <button
            type="button"
            onClick={handleCopy}
            className="flex items-center gap-1.5 text-[11px] text-white/40 hover:text-white/70 transition-colors"
            aria-label="Copy the text"
          >
            {copied ? <Check className="size-3.5 text-emerald-400" /> : <Copy className="size-3.5" />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
        )}
      </div>
      {downloadFailed && (
        <div className="border-t border-amber-500/15 bg-amber-500/5 px-4 py-2 text-[12px] text-amber-300/80">
          {canWord
            ? 'The download didn\u2019t go through. The full text is below, ready to copy.'
            : 'The download didn\u2019t go through. Please try again.'}
        </div>
      )}
      {canWord && showText && (
        <div className="border-t border-emerald-500/10 bg-black/25 px-4 py-3">
          {textState === 'loading' && (
            <div className="flex items-center gap-2 text-[12px] text-white/40">
              <Loader2 className="size-3.5 animate-spin" />
              <span>Loading the text…</span>
            </div>
          )}
          {textState === 'error' && (
            <div className="text-[12px] text-red-300/80">
              Couldn&apos;t load the text. Try the PDF or Word download instead.
            </div>
          )}
          {text !== null && textState !== 'loading' && (
            <div className="max-h-80 overflow-auto rounded-md border border-white/5 bg-black/30 p-3">
              <pre className="m-0 whitespace-pre-wrap break-words font-sans text-[12.5px] leading-relaxed text-white/75 select-text">
                {text}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
