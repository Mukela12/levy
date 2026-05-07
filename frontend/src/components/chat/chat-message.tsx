'use client'

import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ChevronDown, ChevronUp, FileText, Clock, Scale } from 'lucide-react'
import { MatchBadge } from '@/components/ui/match-badge'
import type { ChunkUsed } from '@/lib/api'

interface ChatMessageProps {
  role: 'user' | 'assistant'
  content: string
  citations?: ChunkUsed[]
  timing?: { total_ms: number }
  isStreaming?: boolean
}

/**
 * Inline SVG tail that grows naturally out of the bottom-right of the user
 * bubble — replaces the previous "two orphan dots" effect that read as AI-generated.
 *
 * The path is a single curve drawn so the tail joins the bubble seamlessly
 * (we use the same fill + stroke as the bubble) and tucks back into the
 * bubble corner. Sized small (~14×14) so it feels like a whisper, not a
 * decoration.
 */
function UserBubbleTail() {
  return (
    <svg
      width="18"
      height="14"
      viewBox="0 0 18 14"
      className="absolute -bottom-[6px] right-3 pointer-events-none"
      aria-hidden="true"
    >
      {/* Tail body — same green-tinted glass as the bubble */}
      <path
        d="M0 0 C 4 6, 9 10, 16 12 C 11 12, 5 8, 2 0 Z"
        fill="rgba(34, 197, 94, 0.08)"
        stroke="rgba(34, 197, 94, 0.18)"
        strokeWidth="0.75"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function ChatMessage({ role, content, citations, timing, isStreaming }: ChatMessageProps) {
  const [showCitations, setShowCitations] = useState(false)

  if (role === 'user') {
    return (
      <div className="flex justify-end px-4 md:px-0">
        <div className="relative max-w-[78%] md:max-w-[70%]">
          <div
            className="px-5 py-3.5 text-[14px] leading-relaxed text-white/90 rounded-2xl rounded-br-md relative"
            style={{
              background:
                'linear-gradient(135deg, rgba(34, 197, 94, 0.10) 0%, rgba(34, 197, 94, 0.06) 100%)',
              border: '1px solid rgba(34, 197, 94, 0.18)',
              boxShadow:
                '0 8px 24px -12px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.04)',
            }}
          >
            {content}
          </div>
          <UserBubbleTail />
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-3 px-4 md:px-0">
      <div className="flex-1 min-w-0 space-y-2.5">
        {/* AI Card Container */}
        <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] border-l-[3px] border-l-emerald-500/40 px-4 py-4">
          {/* AI Avatar Header */}
          <div className="flex items-center gap-2 mb-3">
            <div className="w-6 h-6 rounded-full bg-emerald-500/10 flex items-center justify-center">
              <Scale className="w-3 h-3 text-emerald-400" />
            </div>
            <span
              className="text-[11px] font-medium text-white/30 tracking-wide uppercase"
              style={{ fontFamily: "'Playfair Display', serif" }}
            >
              Levy AI
            </span>
          </div>

          {/* Content */}
          <div className="text-[14px] leading-[1.7] text-white/75 [&_h2]:text-white/90 [&_h2]:text-[14.5px] [&_h2]:font-semibold [&_h2]:mt-4 [&_h2]:mb-1.5 [&_strong]:text-white/85 [&_li]:text-white/70 [&_li]:mb-1 [&_code]:text-emerald-400/70 [&_code]:bg-white/[0.04] [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-[12.5px] [&_p]:mb-2">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
            {isStreaming && !content && (
              <div className="flex items-center gap-1 py-2">
                <span className="w-1 h-1 rounded-full bg-white/30 animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1 h-1 rounded-full bg-white/30 animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1 h-1 rounded-full bg-white/30 animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            )}
            {isStreaming && content && (
              <span className="inline-block w-px h-3.5 bg-white/40 animate-pulse ml-0.5" />
            )}
          </div>
        </div>

        {/* Citations */}
        {citations && citations.length > 0 && (
          <div className="space-y-2 pt-1">
            <button
              onClick={() => setShowCitations(!showCitations)}
              className="flex items-center gap-1.5 text-[11px] text-white/25 hover:text-white/40 transition-colors"
            >
              <FileText className="w-3 h-3" />
              <span>{citations.length} source{citations.length !== 1 ? 's' : ''}</span>
              {showCitations ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>

            {showCitations && (
              <div className="space-y-1.5">
                {citations.map((cite, i) => (
                  <div
                    key={cite.id || i}
                    className="px-3.5 py-3 rounded-lg bg-white/[0.02] border border-white/[0.05] space-y-1.5 hover:border-white/[0.08] transition-colors"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-[12px] font-semibold text-emerald-400/80 truncate">
                          {cite.act_name}
                        </span>
                        {cite.section && (
                          <>
                            <span className="w-px h-3 bg-white/10" />
                            <span className="text-[11px] text-white/25 flex-shrink-0">
                              S.{cite.section}{cite.part ? ` Pt.${cite.part}` : ''}
                            </span>
                          </>
                        )}
                      </div>
                      <MatchBadge percentage={Math.round(cite.similarity * 100)} />
                    </div>
                    {cite.content_preview && (
                      <p className="text-[11px] text-white/25 leading-relaxed line-clamp-2">{cite.content_preview}</p>
                    )}
                    {cite.page_start && (
                      <p className="text-[10px] text-white/15">
                        p.{cite.page_start}{cite.page_end && cite.page_end !== cite.page_start ? `–${cite.page_end}` : ''}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {timing && (
          <div className="flex items-center gap-1 text-[10px] text-white/15">
            <Clock className="w-2.5 h-2.5" />
            <span>{(timing.total_ms / 1000).toFixed(1)}s</span>
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * ThinkingGlow - displayed between user message and AI response while loading
 */
export function ThinkingGlow() {
  return (
    <div className="flex justify-start px-4">
      <div
        className="w-full max-w-xl h-20 rounded-2xl animate-pulse"
        style={{
          background: 'radial-gradient(ellipse at center, rgba(34,197,94,0.12) 0%, transparent 70%)',
        }}
      />
    </div>
  )
}
