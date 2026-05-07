'use client'

import { useState, useRef, useEffect } from 'react'
import { Paperclip, Loader2, ArrowUp, Globe } from 'lucide-react'

interface ChatInputProps {
  onSend: (message: string, options?: { webSearch?: boolean }) => void
  disabled?: boolean
  placeholder?: string
}

export function ChatInput({ onSend, disabled, placeholder = 'Ask about Zambian law...' }: ChatInputProps) {
  const [message, setMessage] = useState('')
  const [webSearch, setWebSearch] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
    }
  }, [message])

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
        className={`relative rounded-2xl transition-all duration-200 ${
          hasContent ? 'border-emerald-500/30' : 'border-white/[0.06]'
        }`}
        style={{
          background: 'rgba(255, 255, 255, 0.03)',
          backdropFilter: 'blur(12px)',
          border: hasContent
            ? '1px solid rgba(34, 197, 94, 0.3)'
            : '1px solid rgba(255, 255, 255, 0.06)',
          boxShadow: '0 4px 24px -4px rgba(0, 0, 0, 0.3)',
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
            <button className="flex items-center justify-center size-8 rounded-lg text-white/20 hover:text-white/50 hover:bg-white/[0.04] transition-all">
              <Paperclip className="size-4" />
            </button>
            <button
              onClick={() => setWebSearch(!webSearch)}
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
            className={`flex items-center justify-center size-9 rounded-xl transition-all duration-200 active:scale-95 ${
              hasContent && !disabled
                ? 'bg-emerald-600 hover:bg-emerald-500 text-white'
                : 'bg-white/[0.04] text-white/15 cursor-not-allowed'
            }`}
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
