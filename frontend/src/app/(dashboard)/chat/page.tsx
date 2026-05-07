'use client'

import { useState, useRef, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/components/auth/auth-provider'
import { createClient } from '@/lib/supabase'
import { streamQuery } from '@/lib/api'
import { ChatInput } from '@/components/chat/chat-input'
import { ChatMessage, ThinkingGlow } from '@/components/chat/chat-message'
import { BriefPanel } from '@/components/chat/brief-panel'
import { BookOpen, Search, FileText, Gavel, Scale, X } from 'lucide-react'
import type { ChunkUsed } from '@/lib/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
  citations?: ChunkUsed[]
  timing?: { total_ms: number }
}

function getGreeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

const quickActions = [
  {
    icon: Gavel,
    label: 'Criminal Law',
    description: 'Rights of arrested persons in Zambia',
  },
  {
    icon: BookOpen,
    label: 'Company Registration',
    description: 'How to register a company with PACRA',
  },
  {
    icon: Search,
    label: 'Employment Law',
    description: 'Employment Code on termination',
  },
  {
    icon: FileText,
    label: 'Environmental',
    description: 'Environmental requirements for mining',
  },
]

export default function NewChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [showMobileBrief, setShowMobileBrief] = useState(false)
  const [accentLineWidth, setAccentLineWidth] = useState(0)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { user, session } = useAuth()
  const router = useRouter()

  // Animate accent line on mount
  useEffect(() => {
    const timer = setTimeout(() => setAccentLineWidth(64), 100)
    return () => clearTimeout(timer)
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function createSession(firstMessage: string): Promise<string> {
    const supabase = createClient()
    const title = firstMessage.length > 60 ? firstMessage.slice(0, 57) + '...' : firstMessage
    const { data, error } = await supabase
      .from('chat_sessions')
      .insert({ user_id: user?.id, title })
      .select('id')
      .single()

    if (error) throw error
    return data.id
  }

  async function saveMessage(sid: string, role: string, content: string, citations?: ChunkUsed[]) {
    const supabase = createClient()
    await supabase.from('chat_messages').insert({
      session_id: sid,
      role,
      content,
      citations: citations || null,
    })
  }

  async function handleSend(question: string) {
    setLoading(true)
    const userMsg: Message = { role: 'user', content: question }
    setMessages((prev) => [...prev, userMsg])

    try {
      // Create session if first message
      let sid = sessionId
      if (!sid) {
        sid = await createSession(question)
        setSessionId(sid)
      }

      await saveMessage(sid, 'user', question)

      // Add placeholder assistant message for streaming
      const assistantMsg: Message = { role: 'assistant', content: '', citations: [] }
      setMessages((prev) => [...prev, assistantMsg])

      await streamQuery(
        question,
        { token: session?.access_token },
        (chunk) => {
          setMessages((prev) => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            updated[updated.length - 1] = { ...last, content: last.content + chunk }
            return updated
          })
        },
        (metadata) => {
          setMessages((prev) => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            updated[updated.length - 1] = {
              ...last,
              citations: metadata.chunks_used,
              timing: { total_ms: metadata.timing?.total_ms ?? 0 },
            }
            return updated
          })

          // Save the final assistant message
          setMessages((prev) => {
            const last = prev[prev.length - 1]
            saveMessage(sid!, 'assistant', last.content, last.citations)
            return prev
          })

          setLoading(false)
        }
      )

      // Update URL to session
      router.replace(`/chat/${sid}`, { scroll: false })
    } catch (err) {
      const errorMsg: Message = {
        role: 'assistant',
        content: 'Sorry, I encountered an error processing your question. Please try again.',
      }
      setMessages((prev) => {
        // Replace the empty streaming message if it exists, otherwise append
        const last = prev[prev.length - 1]
        if (last && last.role === 'assistant' && last.content === '') {
          return [...prev.slice(0, -1), errorMsg]
        }
        return [...prev, errorMsg]
      })
      setLoading(false)
    }
  }

  const hasMessages = messages.length > 0
  const displayName = user?.user_metadata?.full_name || user?.email?.split('@')[0] || 'Counsel'

  return (
    <div className="flex flex-1 overflow-hidden" style={{ overscrollBehavior: 'none' }}>
      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {!hasMessages ? (
          /* ── Welcome State ── */
          <div className="flex-1 flex flex-col items-center justify-center px-4 relative">
            {/* Subtle radial background */}
            <div
              className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[500px] h-[400px] pointer-events-none"
              style={{ background: 'radial-gradient(ellipse at center, rgba(34, 197, 94, 0.04) 0%, transparent 70%)' }}
            />

            <div className="text-center mb-8 space-y-4 relative z-10">
              {/* Emerald accent line - animates width */}
              <div
                className="mx-auto h-[2px] rounded-full bg-gradient-to-r from-transparent via-emerald-500/60 to-transparent mb-6 transition-all duration-1000 ease-out"
                style={{ width: `${accentLineWidth}px` }}
              />

              {/* Personalized greeting */}
              <h1
                className="text-3xl font-bold text-foreground tracking-tight"
                style={{ fontFamily: "'Playfair Display', serif" }}
              >
                {getGreeting()}, {displayName}
              </h1>
              <p
                className="text-[15px] text-muted-foreground/60 italic"
                style={{ fontFamily: "'Playfair Display', serif" }}
              >
                Your counsel awaits
              </p>
            </div>

            {/* Quick Action Cards - 2x2 grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 mb-8 max-w-2xl w-full relative z-10">
              {quickActions.map((action, i) => (
                <button
                  key={i}
                  onClick={() => handleSend(action.description)}
                  className="flex items-start gap-3 p-4 rounded-xl text-left transition-all duration-200 group hover:scale-[1.01] active:scale-[0.99] border border-white/[0.06] bg-white/[0.02] hover:border-emerald-500/20 hover:bg-emerald-500/[0.04]"
                >
                  <action.icon className="w-5 h-5 text-white/20 group-hover:text-emerald-400/70 transition-colors flex-shrink-0 mt-0.5" />
                  <div>
                    <div className="text-[13px] font-medium text-white/60 group-hover:text-white/90 transition-colors">
                      {action.label}
                    </div>
                    <div className="text-[11px] text-white/30 group-hover:text-white/50 transition-colors mt-0.5 leading-relaxed">
                      {action.description}
                    </div>
                  </div>
                </button>
              ))}
            </div>

            <div className="w-full max-w-3xl relative z-10">
              <ChatInput onSend={handleSend} disabled={loading} />
            </div>

            <p className="mt-4 text-[10px] text-white/15 relative z-10">
              Levy provides legal information, not legal advice. Always consult a qualified lawyer.
            </p>
          </div>
        ) : (
          /* ── Chat State ── */
          <>
            <div
              className="flex-1 overflow-y-auto py-6"
              style={{ overscrollBehavior: 'none' }}
            >
              <div className="max-w-3xl mx-auto space-y-6">
                {messages.map((msg, i) => {
                  const isLastAssistant = loading && i === messages.length - 1 && msg.role === 'assistant'
                  return (
                    <div key={i}>
                      {/* Show ThinkingGlow between user message and empty assistant response */}
                      {isLastAssistant && !msg.content && <ThinkingGlow />}
                      {(!isLastAssistant || msg.content) && (
                        <ChatMessage
                          role={msg.role}
                          content={msg.content}
                          citations={msg.citations}
                          timing={msg.timing}
                          isStreaming={isLastAssistant}
                        />
                      )}
                    </div>
                  )
                })}
                <div ref={messagesEndRef} />
              </div>
            </div>
            <div className="px-4 py-4 border-t border-white/[0.06]">
              <ChatInput onSend={handleSend} disabled={loading} />
              <p className="mt-2 text-center text-[10px] text-[#5a5a5f]">
                Levy provides legal information, not legal advice.
              </p>
            </div>
          </>
        )}
      </div>

      {/* Brief Panel - desktop only, when conversation active */}
      {hasMessages && (
        <aside className="hidden lg:flex flex-col w-[280px] shrink-0 border-l border-white/[0.06] bg-[#0d0d0f]">
          <BriefPanel messages={messages.map(m => ({ role: m.role, content: m.content }))} token={session?.access_token} />
        </aside>
      )}

      {/* Mobile brief button - top right, only when conversation active */}
      {hasMessages && (
        <button
          onClick={() => setShowMobileBrief(true)}
          className="lg:hidden fixed top-1 right-14 z-40 w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 hover:bg-emerald-500/20 transition-colors"
        >
          <Scale size={16} />
        </button>
      )}

      {/* Mobile brief bottom sheet */}
      {showMobileBrief && (
        <div className="lg:hidden fixed inset-0 z-50 flex flex-col">
          <div
            className="flex-1 bg-black/60 backdrop-blur-sm"
            onClick={() => setShowMobileBrief(false)}
          />
          <div className="bg-[#0d0d0f] border-t border-white/[0.06] rounded-t-2xl max-h-[70vh] flex flex-col">
            <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.06]">
              <span
                className="text-xs font-bold tracking-[0.2em] uppercase text-emerald-400"
                style={{ fontFamily: "'Playfair Display', serif" }}
              >
                The Brief
              </span>
              <button
                onClick={() => setShowMobileBrief(false)}
                className="p-1.5 rounded-lg hover:bg-white/[0.04] text-white/30 hover:text-white/60 transition-colors"
              >
                <X size={16} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto" style={{ overscrollBehavior: 'contain' }}>
              <BriefPanel messages={messages.map(m => ({ role: m.role, content: m.content }))} token={session?.access_token} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
