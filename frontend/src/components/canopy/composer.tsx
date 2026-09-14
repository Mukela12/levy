'use client'

/**
 * Canopy's composer. Same contract as the legacy ChatInput (onSend, disabled,
 * webSearch, attach/upload callbacks, seed) plus an optional mode control
 * that exposes the one real mode production has: review a pasted draft.
 * Enter sends, Shift+Enter breaks a line, exactly as before.
 */

import { useEffect, useRef, useState } from 'react'
import { ArrowUp, ChevronDown, Globe, Library, Loader2, Upload } from 'lucide-react'
import LordIcon from '@/components/ui/lord-icon'
import { CANOPY_ICON } from './icons'

export type ComposerMode = 'research' | 'review'

export interface CanopyComposerProps {
  onSend: (message: string, options?: { webSearch?: boolean }) => void
  disabled?: boolean
  placeholder?: string
  webSearch?: boolean
  onWebSearchChange?: (next: boolean) => void
  onAttachClick?: () => void
  onUploadFile?: (file: File) => Promise<void>
  attachmentCount?: number
  seed?: { text: string; nonce: number }
  /** When provided, a Research / Review draft control is shown. */
  mode?: ComposerMode
  onModeChange?: (mode: ComposerMode) => void
  compact?: boolean
  /** Rendered above the textarea (attached-document chips). */
  strip?: React.ReactNode
}

export function CanopyComposer({
  onSend,
  disabled,
  placeholder,
  webSearch: webSearchProp,
  onWebSearchChange,
  onAttachClick,
  onUploadFile,
  attachmentCount = 0,
  seed,
  mode,
  onModeChange,
  compact = false,
  strip,
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

  useEffect(() => {
    if (!attachMenuOpen) return
    const handler = (e: MouseEvent) => {
      if (!attachWrapRef.current?.contains(e.target as Node)) setAttachMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
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
    try {
      await onUploadFile(file)
    } catch (err) {
      console.error('chat upload failed', err)
    } finally {
      setUploadingFile(false)
    }
  }

  const submit = () => {
    if (message.trim() && !disabled) {
      onSend(message.trim(), { webSearch })
      setMessage('')
      if (textareaRef.current) textareaRef.current.style.height = 'auto'
    }
  }
  const hasContent = message.trim().length > 0
  const showAttach = !!(onAttachClick || onUploadFile)
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
            <div ref={attachWrapRef} className="cp-attach">
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
              {attachMenuOpen && (
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
            <label className="cp-mode">
              <span className="sr-only">Question mode</span>
              <select aria-label="Question mode" value={mode ?? 'research'} onChange={(e) => onModeChange(e.target.value as ComposerMode)}>
                <option value="research">Research</option>
                <option value="review">Review draft</option>
              </select>
              <ChevronDown size={14} aria-hidden="true" />
            </label>
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
        <button type="submit" className="cp-send" aria-label="Send question" disabled={!hasContent || disabled}>
          {disabled ? <Loader2 size={18} className="animate-spin" /> : <ArrowUp size={20} />}
        </button>
      </div>
    </form>
  )
}
