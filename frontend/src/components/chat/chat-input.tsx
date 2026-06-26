'use client'

import { useState, useRef, useEffect } from 'react'
import { Paperclip, Loader2, ArrowUp, Globe, Upload, Library } from 'lucide-react'

interface ChatInputProps {
  onSend: (message: string, options?: { webSearch?: boolean }) => void
  disabled?: boolean
  placeholder?: string
  webSearch?: boolean
  onWebSearchChange?: (next: boolean) => void
  /** Opens the library picker (existing flow). When undefined the option is hidden. */
  onAttachClick?: () => void
  /**
   * Direct file upload from the composer. Receives a single picked File and is
   * expected to upload + attach it to the active session. When undefined the
   * "Upload file" menu item is hidden.
   */
  onUploadFile?: (file: File) => Promise<void>
  /** Number of currently-attached docs; surfaced as a small badge. */
  attachmentCount?: number
  /**
   * Imperatively seed the textarea (e.g. the "Review my draft" starter
   * pre-fills a primer so the user pastes their draft right after, instead
   * of firing an empty turn). Bump `nonce` to re-trigger with the same text.
   */
  seed?: { text: string; nonce: number }
}

export function ChatInput({
  onSend,
  disabled,
  placeholder = 'Ask about Zambian law...',
  webSearch: webSearchProp,
  onWebSearchChange,
  onAttachClick,
  onUploadFile,
  attachmentCount = 0,
  seed,
}: ChatInputProps) {
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

  // Dismiss the attachment popover on outside click.
  useEffect(() => {
    if (!attachMenuOpen) return
    const handler = (e: MouseEvent) => {
      if (!attachWrapRef.current?.contains(e.target as Node)) setAttachMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [attachMenuOpen])

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    // Reset so picking the same file twice still fires onChange.
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

  const showAttachButton = !!(onAttachClick || onUploadFile)

  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
    }
  }, [message])

  // Seed the box + drop the caret at the end so the user can paste/type
  // straight after the primer. Keyed on nonce so repeat clicks re-seed.
  useEffect(() => {
    if (!seed || !seed.text) return
    setMessage(seed.text)
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

  const handleSubmit = () => {
    if (message.trim() && !disabled) {
      onSend(message.trim(), { webSearch })
      setMessage('')
      if (textareaRef.current) textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const hasContent = message.trim().length > 0

  return (
    <div className="relative w-full max-w-3xl mx-auto">
      <div
        data-tour="chat-input"
        className="relative rounded-2xl transition-all duration-200"
        style={{
          background:
            'color-mix(in oklab, rgb(20 20 22) 78%, transparent)',
          backdropFilter: 'blur(22px) saturate(150%)',
          WebkitBackdropFilter: 'blur(22px) saturate(150%)',
          border: hasContent
            ? '1px solid rgba(34, 197, 94, 0.35)'
            : '1px solid rgba(255, 255, 255, 0.08)',
          boxShadow: hasContent
            ? '0 24px 60px -28px rgba(0,0,0,0.55), 0 8px 24px -12px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.06), 0 0 0 4px rgba(34,197,94,0.08)'
            : '0 24px 60px -28px rgba(0,0,0,0.55), 0 8px 24px -12px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.05)',
        }}
      >
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          className="w-full resize-none bg-transparent text-[14.5px] text-white/90 placeholder-white/20 px-5 pt-4 pb-2 focus:outline-none min-h-[56px] max-h-[200px] disabled:opacity-40"
          rows={1}
        />
        <div className="flex items-center justify-between px-3 pb-3">
          <div className="flex items-center gap-1">
            {/* Hidden picker that the popover triggers. */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={handleFileSelected}
            />
            {showAttachButton && (
              <div ref={attachWrapRef} className="relative">
                <button
                  type="button"
                  onClick={() => setAttachMenuOpen((o) => !o)}
                  disabled={disabled || uploadingFile}
                  data-tour="attachments"
                  aria-haspopup="menu"
                  aria-expanded={attachMenuOpen}
                  aria-label={
                    attachmentCount > 0
                      ? `Attach documents (${attachmentCount} already attached)`
                      : 'Attach documents'
                  }
                  className={`relative flex items-center justify-center size-8 rounded-lg transition-all ${
                    attachmentCount > 0 || attachMenuOpen
                      ? 'bg-emerald-500/12 text-emerald-400 border border-emerald-500/25'
                      : 'text-white/20 hover:text-white/50 hover:bg-white/[0.04]'
                  } disabled:opacity-30 disabled:cursor-not-allowed`}
                >
                  {uploadingFile ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Paperclip className="size-4" />
                  )}
                  {attachmentCount > 0 && (
                    <span className="absolute -top-1 -right-1 min-w-[16px] h-[16px] px-[3px] rounded-full bg-emerald-500 text-[10px] leading-none font-semibold flex items-center justify-center text-white">
                      {attachmentCount > 9 ? '9+' : attachmentCount}
                    </span>
                  )}
                </button>
                {attachMenuOpen && (
                  <div
                    role="menu"
                    className="absolute bottom-full mb-2 left-0 z-50 min-w-[220px] rounded-xl border border-white/[0.08] bg-[#16161a] shadow-2xl shadow-black/40 backdrop-blur-xl py-1"
                  >
                    {onUploadFile && (
                      <button
                        type="button"
                        role="menuitem"
                        onClick={() => fileInputRef.current?.click()}
                        className="w-full flex items-center gap-2.5 px-3 py-2 text-left text-[12.5px] text-white/80 hover:bg-white/[0.05]"
                      >
                        <Upload className="size-3.5 text-emerald-400/80" />
                        <span className="flex-1">Upload file</span>
                        <span className="text-[10px] text-white/30">PDF</span>
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
                        className="w-full flex items-center gap-2.5 px-3 py-2 text-left text-[12.5px] text-white/80 hover:bg-white/[0.05]"
                      >
                        <Library className="size-3.5 text-emerald-400/80" />
                        <span className="flex-1">From your library</span>
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}
            <button
              onClick={() => setWebSearch(!webSearch)}
              data-tour="web-search"
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-all ${
                webSearch
                  ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
                  : 'text-white/20 hover:text-white/50 hover:bg-white/[0.04]'
              }`}
            >
              <Globe size={14} />
              <span className="text-[11px]">Search</span>
            </button>
          </div>
          <button
            onClick={handleSubmit}
            disabled={!hasContent || disabled}
            aria-label="Send"
            className="flex items-center justify-center size-9 rounded-xl transition-all duration-200 active:scale-95 disabled:cursor-not-allowed"
            style={
              hasContent && !disabled
                ? {
                    background:
                      'linear-gradient(180deg, rgb(16 185 129) 0%, rgb(5 150 105) 100%)',
                    color: 'white',
                    boxShadow:
                      '0 1px 0 0 rgba(255,255,255,0.2) inset, 0 0 0 1px rgba(16,185,129,0.45), 0 8px 20px -8px rgba(16,185,129,0.55)',
                  }
                : {
                    background: 'rgba(255,255,255,0.04)',
                    color: 'rgba(255,255,255,0.15)',
                  }
            }
          >
            {disabled ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <ArrowUp className="size-4" />
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
