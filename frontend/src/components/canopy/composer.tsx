'use client'

/**
 * Canopy's composer. Same contract as the legacy ChatInput (onSend, disabled,
 * webSearch, attach/upload callbacks, seed) plus an optional mode control
 * that exposes the one real mode production has: review a pasted draft.
 * Enter sends, Shift+Enter breaks a line, exactly as before.
 */

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { ArrowUp, Globe, Library, Loader2, LogIn, Upload, UserPlus } from 'lucide-react'
import { ChoiceSelect } from './choice-select'
import LordIcon from '@/components/ui/lord-icon'
import { CANOPY_ICON } from './icons'

export type ComposerMode = 'research' | 'review'

const DRAFT_KEY = 'levy:composer-draft'

export interface CanopyComposerProps {
  onSend: (message: string, options?: { webSearch?: boolean }) => void
  disabled?: boolean
  placeholder?: string
  webSearch?: boolean
  onWebSearchChange?: (next: boolean) => void
  onAttachClick?: () => void
  onUploadFile?: (file: File) => Promise<void>
  /** Signed-out visitors: show the attach button anyway and explain that
   *  files need an account. Most phone visitors are guests, so without this
   *  nobody on a phone ever saw that Levy reads documents. */
  attachNeedsAccount?: boolean
  attachmentCount?: number
  seed?: { text: string; nonce: number }
  /** When provided, a Research / Review draft control is shown. */
  mode?: ComposerMode
  onModeChange?: (mode: ComposerMode) => void
  compact?: boolean
  /** Rendered above the textarea (attached-document chips). */
  strip?: React.ReactNode
  onDraftPresenceChange?: (hasDraft: boolean) => void
}

export function CanopyComposer({
  onSend,
  disabled,
  placeholder,
  webSearch: webSearchProp,
  onWebSearchChange,
  onAttachClick,
  onUploadFile,
  attachNeedsAccount = false,
  attachmentCount = 0,
  seed,
  mode,
  onModeChange,
  compact = false,
  strip,
  onDraftPresenceChange,
}: CanopyComposerProps) {
  const [message, setMessage] = useState('')
  const [webSearchInternal, setWebSearchInternal] = useState(false)
  const webSearch = webSearchProp ?? webSearchInternal
  const setWebSearch = (next: boolean) => {
    if (onWebSearchChange) onWebSearchChange(next)
    else setWebSearchInternal(next)
  }
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const attachWrapRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [attachMenuOpen, setAttachMenuOpen] = useState(false)
  const [uploadingFile, setUploadingFile] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  useEffect(() => { onDraftPresenceChange?.(Boolean(message.trim())) }, [message, onDraftPresenceChange])

  useEffect(() => {
    try {
      const kept = sessionStorage.getItem(DRAFT_KEY)
      if (kept) {
        sessionStorage.removeItem(DRAFT_KEY)
        setMessage((m) => m || kept)
      }
    } catch { /* storage unavailable */ }
  }, [])

  useEffect(() => {
    if (!attachMenuOpen) return
    const frame = requestAnimationFrame(() => attachWrapRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus())
    const handler = (e: MouseEvent) => {
      if (!attachWrapRef.current?.contains(e.target as Node)) setAttachMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => { cancelAnimationFrame(frame); document.removeEventListener('mousedown', handler) }
  }, [attachMenuOpen])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const min = compact ? 48 : 84
    el.style.height = `${Math.min(200, Math.max(min, el.scrollHeight))}px`
  }, [message, compact])

  // Seed the box and put the caret at the end. An empty seed only focuses.
  useEffect(() => {
    if (!seed) return
    if (seed.text) setMessage(seed.text)
    const el = textareaRef.current
    if (el) {
      el.focus()
      requestAnimationFrame(() => {
        el.selectionStart = el.selectionEnd = el.value.length
        el.scrollTop = el.scrollHeight
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed?.nonce])

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || !onUploadFile) return
    setAttachMenuOpen(false)
    setUploadingFile(true)
    setUploadError(null)
    try {
      await onUploadFile(file)
    } catch {
      setUploadError('Your file could not be attached. Please try again before sending your question.')
    } finally {
      setUploadingFile(false)
    }
  }

  const submit = () => {
    if (message.trim() && !disabled && !uploadingFile) {
      onSend(message.trim(), { webSearch })
      setMessage('')
      if (textareaRef.current) textareaRef.current.style.height = 'auto'
    }
  }
  const hasContent = message.trim().length > 0
  const canAttach = !!(onAttachClick || onUploadFile)
  const showAttach = canAttach || attachNeedsAccount
  // Keep what a guest typed across sign-in (same tab, so OAuth round trips too).
  const keepDraft = () => {
    try { if (message.trim()) sessionStorage.setItem(DRAFT_KEY, message) } catch { /* private mode */ }
  }
  const effectivePlaceholder =
    placeholder ?? (mode === 'review' ? 'Paste your draft, then tell Levy what to review…' : 'Ask a question about Zambian law…')

  return (
    <form
      className={'cp-composer' + (compact ? ' is-compact' : '')}
      data-tour="chat-input"
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
    >
      {strip}
      {uploadError && <p role="alert" className="px-4 pt-3 text-sm text-destructive">{uploadError}</p>}
      {uploadingFile && <p role="status" className="px-4 pt-3 text-sm text-muted-foreground">Attaching your file…</p>}
      <label className="sr-only" htmlFor="cp-question">Your question about Zambian law</label>
      <textarea
        ref={textareaRef}
        id="cp-question"
        name="question"
        enterKeyHint="send"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            submit()
          }
        }}
        placeholder={effectivePlaceholder}
        disabled={disabled}
        rows={1}
      />
      <div className="cp-composer-bottom">
        <div className="cp-composer-tools">
          <input ref={fileInputRef} type="file" accept=".pdf" className="hidden" onChange={handleFileSelected} />
          {showAttach && (
            <div ref={attachWrapRef} className="cp-attach" onKeyDown={(event) => {
              if (!attachMenuOpen) return
              if (event.key === 'Escape') {
                event.preventDefault()
                event.stopPropagation()
                setAttachMenuOpen(false)
                attachWrapRef.current?.querySelector<HTMLButtonElement>('[aria-haspopup="menu"]')?.focus()
              } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
                event.preventDefault()
                const items = Array.from(attachWrapRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])
                const current = items.indexOf(document.activeElement as HTMLElement)
                const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (current + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length
                items[next]?.focus()
              } else if (event.key === 'Tab') setAttachMenuOpen(false)
            }}>
              <button
                type="button"
                className={'cp-icon-btn' + (attachmentCount > 0 || attachMenuOpen ? ' is-active' : '')}
                onClick={() => setAttachMenuOpen((o) => !o)}
                disabled={disabled || uploadingFile}
                data-tour="attachments"
                aria-haspopup="menu"
                aria-expanded={attachMenuOpen}
                aria-label={attachmentCount > 0 ? `Attach documents (${attachmentCount} already attached)` : 'Attach documents'}
              >
                {uploadingFile ? <Loader2 size={18} className="animate-spin" /> : <LordIcon name={CANOPY_ICON.plus} size={21} />}
                {attachmentCount > 0 && <span className="cp-attach-count">{attachmentCount > 9 ? '9+' : attachmentCount}</span>}
              </button>
              {attachMenuOpen && !canAttach && (
                <div role="menu" className="cp-menu is-guest">
                  <p className="cp-menu-note">Attach PDFs or files from your library with a free account. What you typed stays here.</p>
                  <Link role="menuitem" href="/auth/signup" onClick={keepDraft}>
                    <UserPlus size={15} />
                    <span>Create a free account</span>
                  </Link>
                  <Link role="menuitem" href="/auth/login" onClick={keepDraft}>
                    <LogIn size={15} />
                    <span>Sign in</span>
                  </Link>
                </div>
              )}
              {attachMenuOpen && canAttach && (
                <div role="menu" className="cp-menu">
                  {onUploadFile && (
                    <button type="button" role="menuitem" onClick={() => fileInputRef.current?.click()}>
                      <Upload size={15} />
                      <span>Upload file</span>
                      <small>PDF</small>
                    </button>
                  )}
                  {onAttachClick && (
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setAttachMenuOpen(false)
                        onAttachClick()
                      }}
                    >
                      <Library size={15} />
                      <span>From your library</span>
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
          {onModeChange && (
            <div className="cp-mode">
              <ChoiceSelect aria-label="Question mode" value={mode ?? 'research'} onChange={(e) => onModeChange(e.target.value as ComposerMode)}>
                <option value="research">Research</option>
                <option value="review">Review draft</option>
              </ChoiceSelect>
            </div>
          )}
          <button
            type="button"
            className={'cp-web-toggle' + (webSearch ? ' is-active' : '')}
            aria-pressed={webSearch}
            data-tour="web-search"
            title={webSearch ? 'Also search the web with this question' : 'Library sources only'}
            aria-label={webSearch ? 'Disable web search' : 'Enable web search'}
            onClick={() => setWebSearch(!webSearch)}
          >
            <Globe size={16} />
            <span>Web {webSearch ? 'on' : 'off'}</span>
          </button>
        </div>
        <button type="submit" className="cp-send" aria-label="Send question" disabled={!hasContent || disabled || uploadingFile}>
          {disabled ? <Loader2 size={18} className="animate-spin" /> : <ArrowUp size={20} />}
        </button>
      </div>
    </form>
  )
}
