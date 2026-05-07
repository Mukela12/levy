'use client'

import { useState, useRef, useEffect, use } from 'react'
import { useAuth } from '@/components/auth/auth-provider'
import { createClient } from '@/lib/supabase'
import { streamQuery } from '@/lib/api'
import { ChatInput } from '@/components/chat/chat-input'
import { ChatMessage, ThinkingGlow } from '@/components/chat/chat-message'
import { BriefPanel } from '@/components/chat/brief-panel'
import { useRegisterBrief } from '@/components/chat/brief-context'
import { Loader2 } from 'lucide-react'
import type { ChunkUsed } from '@/lib/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
  citations?: ChunkUsed[]
  timing?: { total_ms: number }
}

export default function ChatSessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [initialLoading, setInitialLoading] = useState(true)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { session } = useAuth()

  useRegisterBrief(
    messages.map((m) => ({ role: m.role, content: m.content })),
    session?.access_token,
  )

  useEffect(() => {
    loadMessages()
  }, [id])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function loadMessages() {
    setInitialLoading(true)
    const supabase = createClient()
    const { data } = await supabase
      .from('chat_messages')
      .select('role, content, citations')
      .eq('session_id', id)
      .order('created_at', { ascending: true })

    if (data) {
      setMessages(
        data.map((m) => ({
          role: m.role as 'user' | 'assistant',
          content: m.content,
          citations: m.citations as ChunkUsed[] | undefined,
        }))
      )
    }
    setInitialLoading(false)
  }

  async function saveMessage(role: string, content: string, citations?: ChunkUsed[]) {
    const supabase = createClient()
    await supabase.from('chat_messages').insert({
      session_id: id,
      role,
      content,
      citations: citations || null,
    })
  }

  async function handleSend(question: string) {
    setLoading(true)
    setMessages((prev) => [...prev, { role: 'user', content: question }])

    try {
      await saveMessage('user', question)

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
            saveMessage('assistant', last.content, last.citations)
            return prev
          })

          setLoading(false)
        }
      )
    } catch {
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        if (last && last.role === 'assistant' && last.content === '') {
          return [...prev.slice(0, -1), { role: 'assistant' as const, content: 'Sorry, I encountered an error. Please try again.' }]
        }
        return [...prev, { role: 'assistant' as const, content: 'Sorry, I encountered an error. Please try again.' }]
      })
      setLoading(false)
    }
  }

  if (initialLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-emerald-400 animate-spin" />
      </div>
    )
  }

  const hasMessages = messages.length > 0

  return (
    <div className="flex flex-1 overflow-hidden" style={{ overscrollBehavior: 'none' }}>
      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        <div
          className="flex-1 overflow-y-auto pt-6 pb-40 md:pb-32"
          style={{ overscrollBehavior: 'none' }}
        >
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.map((msg, i) => {
              const isLastAssistant = loading && i === messages.length - 1 && msg.role === 'assistant'
              return (
                <div key={i}>
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
        {/* Floating glass dock — chat input */}
        <div className="absolute inset-x-0 bottom-0 z-20 pointer-events-none">
          <div
            className="px-3 sm:px-4 pt-6 pb-[max(12px,env(safe-area-inset-bottom))]"
            style={{
              background:
                'linear-gradient(to top, rgba(10,10,11,0.95) 0%, rgba(10,10,11,0.6) 60%, transparent 100%)',
            }}
          >
            <div className="pointer-events-auto max-w-3xl mx-auto">
              <ChatInput onSend={handleSend} disabled={loading} />
              <p className="mt-2 text-center text-[10px] text-white/25">
                Levy provides legal information, not legal advice.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Brief Panel - desktop only */}
      {hasMessages && (
        <aside className="hidden lg:flex flex-col w-[280px] shrink-0 border-l border-white/[0.06] bg-[#0d0d0f]">
          <BriefPanel messages={messages.map(m => ({ role: m.role, content: m.content }))} token={session?.access_token} />
        </aside>
      )}
    </div>
  )
}
