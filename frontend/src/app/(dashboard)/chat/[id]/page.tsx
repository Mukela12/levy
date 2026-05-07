'use client'

import { useState, useRef, useEffect, use } from 'react'
import { useAuth } from '@/components/auth/auth-provider'
import { createClient } from '@/lib/supabase'
import { streamQuery } from '@/lib/api'
import { ChatInput } from '@/components/chat/chat-input'
import { ChatMessage, ThinkingGlow } from '@/components/chat/chat-message'
import { BriefPanel } from '@/components/chat/brief-panel'
import { useRegisterBrief } from '@/components/chat/brief-context'
import { usePdfViewer } from '@/components/chat/pdf-viewer-context'
import { useSessionAttachments } from '@/components/chat/use-session-attachments'
import type { ToolCallView } from '@/components/chat/tool-call-card'
import { Loader2, Paperclip, X } from 'lucide-react'
import type { ArtifactView, ChunkUsed, WebSource } from '@/lib/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
  citations?: ChunkUsed[]
  webSources?: WebSource[]
  toolCalls?: ToolCallView[]
  artifacts?: ArtifactView[]
  timing?: { total_ms: number }
  compaction?: { summarised_messages: number; tokens_before: number; tokens_after: number }
}

export default function ChatSessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [initialLoading, setInitialLoading] = useState(true)
  const [webSearch, setWebSearch] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { user, session } = useAuth()
  const pdf = usePdfViewer()
  const attachments = useSessionAttachments(id)

  // Pass the raw messages state (stable reference). Mapping here creates a new
  // array every render and would render-loop with the provider's setState.
  useRegisterBrief(messages, session?.access_token)

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
      .select('role, content, citations, web_sources, artifacts, compaction')
      .eq('session_id', id)
      .order('created_at', { ascending: true })

    if (data) {
      setMessages(
        data.map((m) => ({
          role: m.role as 'user' | 'assistant',
          content: m.content,
          citations: m.citations as ChunkUsed[] | undefined,
          webSources: m.web_sources as WebSource[] | undefined,
          artifacts: m.artifacts as ArtifactView[] | undefined,
          compaction: m.compaction as Message['compaction'] | undefined,
        }))
      )
    }
    setInitialLoading(false)
  }

  async function saveMessage(
    role: string,
    content: string,
    citations?: ChunkUsed[],
    webSources?: WebSource[],
    artifacts?: ArtifactView[],
    compaction?: Message['compaction'],
  ) {
    const supabase = createClient()
    await supabase.from('chat_messages').insert({
      session_id: id,
      role,
      content,
      citations: citations || null,
      web_sources: webSources || null,
      artifacts: artifacts || null,
      compaction: compaction || null,
    })
  }

  async function handleSend(question: string) {
    setLoading(true)
    setMessages((prev) => [...prev, { role: 'user', content: question }])

    try {
      await saveMessage('user', question)

      // Add placeholder assistant message for streaming
      const assistantMsg: Message = {
        role: 'assistant',
        content: '',
        citations: [],
        toolCalls: [],
        artifacts: [],
      }
      setMessages((prev) => [...prev, assistantMsg])

      const updateLast = (patch: (m: Message) => Message) =>
        setMessages((prev) => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          updated[updated.length - 1] = patch(last)
          return updated
        })

      // Send the conversation so far so the backend's compactor can see the
      // full thread when deciding whether to summarise.
      const history = messages
        .filter((m) => m.content)
        .map((m) => ({ role: m.role, content: m.content }))

      await streamQuery(
        question,
        {
          token: session?.access_token,
          webSearch,
          userId: user?.id,
          sessionId: id,
          attachedDocIds: attachments.attachedIds,
          history,
        },
        undefined,
        undefined,
        {
          onToken: (chunk) =>
            updateLast((last) => ({ ...last, content: last.content + chunk })),
          onToolCall: (call) =>
            updateLast((last) => ({
              ...last,
              toolCalls: [
                ...(last.toolCalls ?? []),
                { ...call, status: 'running', db: [], web: [] },
              ],
            })),
          onToolResult: (result) =>
            updateLast((last) => ({
              ...last,
              toolCalls: (last.toolCalls ?? []).map((c) =>
                c.id === result.id
                  ? {
                      ...c,
                      status: result.ok ? 'ok' : 'error',
                      durationMs: result.ms,
                      db: result.db,
                      web: result.web,
                    }
                  : c,
              ),
            })),
          onArtifact: (artifact) =>
            updateLast((last) => {
              const existing = last.artifacts ?? []
              if (existing.some((a) => a.id === artifact.id)) return last
              return { ...last, artifacts: [...existing, artifact] }
            }),
          onCompaction: (info) =>
            updateLast((last) => ({
              ...last,
              compaction: {
                summarised_messages: info.summarised_messages,
                tokens_before: info.tokens_before,
                tokens_after: info.tokens_after,
              },
            })),
          onDone: (metadata) => {
            setMessages((prev) => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              const finalMsg = {
                ...last,
                citations: metadata.chunks_used,
                webSources: metadata.web_sources,
                timing: { total_ms: metadata.timing?.total_ms ?? 0 },
              }
              updated[updated.length - 1] = finalMsg
              saveMessage(
                'assistant',
                finalMsg.content,
                finalMsg.citations,
                finalMsg.webSources,
                finalMsg.artifacts,
                finalMsg.compaction,
              )
              return updated
            })
            setLoading(false)
          },
          onError: (msg) =>
            updateLast((last) => ({
              ...last,
              content:
                (last.content || '') +
                (last.content ? '\n\n' : '') +
                `_Error: ${msg}_`,
            })),
        },
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
              const isLastAssistant =
                loading && i === messages.length - 1 && msg.role === 'assistant'
              const hasResearch = (msg.toolCalls?.length ?? 0) > 0
              const showGlow = isLastAssistant && !msg.content && !hasResearch
              return (
                <div key={i}>
                  {showGlow && <ThinkingGlow />}
                  {!showGlow && (
                    <ChatMessage
                      role={msg.role}
                      content={msg.content}
                      citations={msg.citations}
                      webSources={msg.webSources}
                      toolCalls={msg.toolCalls}
                      artifacts={msg.artifacts}
                      timing={msg.timing}
                      isStreaming={isLastAssistant}
                      compaction={msg.compaction}
                      onOpenCitation={(c) =>
                        pdf.open({
                          documentId: c.document_id,
                          actName: c.act_name,
                          pageStart: c.page_start,
                          pageEnd: c.page_end,
                          section: c.section,
                        })
                      }
                      onOpenArtifact={(a) =>
                        pdf.open({
                          artifactId: a.id,
                          actName: a.title,
                          pageStart: 1,
                        })
                      }
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
              {attachments.attached.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1.5 px-1">
                  {attachments.attached.map((d) => (
                    <button
                      key={d.id}
                      type="button"
                      onClick={() => attachments.detach(d.id)}
                      className="group flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-[11px] text-emerald-100/85 hover:bg-emerald-500/20 transition-colors"
                      aria-label={`Detach ${d.title}`}
                    >
                      <Paperclip size={10} className="text-emerald-400/80" />
                      <span className="max-w-[180px] truncate">{d.title}</span>
                      <X size={10} className="text-emerald-400/40 group-hover:text-emerald-400/80" />
                    </button>
                  ))}
                </div>
              )}
              <ChatInput
                onSend={handleSend}
                disabled={loading}
                webSearch={webSearch}
                onWebSearchChange={setWebSearch}
              />
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
