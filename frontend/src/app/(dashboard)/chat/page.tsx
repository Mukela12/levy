'use client'

import { useState, useRef, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/components/auth/auth-provider'
import { createClient } from '@/lib/supabase'
import { streamQuery } from '@/lib/api'
import { ChatInput } from '@/components/chat/chat-input'
import { ChatMessage, ThinkingGlow } from '@/components/chat/chat-message'
import { BriefPanel } from '@/components/chat/brief-panel'
import { useRegisterBrief } from '@/components/chat/brief-context'
import { usePdfViewer } from '@/components/chat/pdf-viewer-context'
import { AttachmentsSheet } from '@/components/chat/attachments-sheet'
import type { ToolCallView } from '@/components/chat/tool-call-card'
import type { MessageBlock } from '@/components/chat/chat-message'
import { attachDocumentToSession, type LibraryDocument } from '@/lib/api'
import { BookOpen, Search, FileText, Gavel, Paperclip, X } from 'lucide-react'
import { LevyLogo } from '@/components/ui/levy-logo'
import type {
  ApplicationPlan,
  ArtifactView,
  ChunkUsed,
  TemplateSuggestion,
  WebSource,
} from '@/lib/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
  blocks?: MessageBlock[]
  citations?: ChunkUsed[]
  webSources?: WebSource[]
  toolCalls?: ToolCallView[]
  artifacts?: ArtifactView[]
  templateSuggestions?: Record<string, TemplateSuggestion[]>
  applicationPlans?: Record<string, ApplicationPlan>
  timing?: { total_ms: number }
  compaction?: { summarised_messages: number; tokens_before: number; tokens_after: number }
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
  const [accentLineWidth, setAccentLineWidth] = useState(0)
  const [webSearch, setWebSearch] = useState(false)
  // Staged attachments for the very first message: persisted into the
  // chat_session_documents join table once the session is created.
  const [stagedAttachments, setStagedAttachments] = useState<LibraryDocument[]>([])
  const [attachmentsOpen, setAttachmentsOpen] = useState(false)
  const pdf = usePdfViewer()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { user, session } = useAuth()
  const router = useRouter()

  // Expose the raw messages state (stable reference) to the layout-level
  // Brief button + bottom sheet. Do NOT map here - that creates a new array
  // every render and would loop with the provider's setState.
  useRegisterBrief(messages, session?.access_token)

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

  async function saveMessage(
    sid: string,
    role: string,
    content: string,
    citations?: ChunkUsed[],
    webSources?: WebSource[],
    artifacts?: ArtifactView[],
    compaction?: Message['compaction'],
    blocks?: MessageBlock[],
    toolCalls?: ToolCallView[],
  ) {
    const supabase = createClient()
    await supabase.from('chat_messages').insert({
      session_id: sid,
      role,
      content,
      blocks: blocks || null,
      tool_calls: toolCalls || null,
      citations: citations || null,
      web_sources: webSources || null,
      artifacts: artifacts || null,
      compaction: compaction || null,
    })
  }

  async function handleSend(question: string) {
    setLoading(true)
    const userMsg: Message = { role: 'user', content: question }
    setMessages((prev) => [...prev, userMsg])

    // Anonymous mode: keep everything in React state, never touch the DB.
    // Signed-in users get the full session/save flow.
    const isAnonymous = !user

    try {
      // Create session if first message (signed-in only)
      let sid = sessionId
      if (!sid && !isAnonymous) {
        sid = await createSession(question)
        setSessionId(sid)
        // Apply any staged attachments to the new session.
        if (stagedAttachments.length > 0) {
          await Promise.all(
            stagedAttachments.map((d) => attachDocumentToSession(sid!, d.id)),
          )
        }
      }

      if (sid && !isAnonymous) {
        await saveMessage(sid, 'user', question)
      }

      // Add placeholder assistant message for streaming
      const assistantMsg: Message = {
        role: 'assistant',
        content: '',
        blocks: [],
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
          sessionId: sid ?? undefined,
          attachedDocIds: stagedAttachments.map((d) => d.id),
          history,
        },
        undefined,
        undefined,
        {
          onToken: (chunk) =>
            updateLast((last) => {
              // Append the chunk to the trailing text block, or start a new one
              // if the last block is a tool call (means a new prose segment).
              const blocks = [...(last.blocks ?? [])]
              const tail = blocks[blocks.length - 1]
              if (tail && tail.kind === 'text') {
                blocks[blocks.length - 1] = { kind: 'text', text: tail.text + chunk }
              } else {
                blocks.push({ kind: 'text', text: chunk })
              }
              return { ...last, content: last.content + chunk, blocks }
            }),
          onToolCall: (call) =>
            updateLast((last) => ({
              ...last,
              blocks: [...(last.blocks ?? []), { kind: 'tool', toolCallId: call.id }],
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
          onTemplateSuggestion: (event) =>
            updateLast((last) => {
              const blocks = [...(last.blocks ?? [])]
              const existing = blocks.findIndex(
                (b) => b.kind === 'templates' && b.toolCallId === event.tool_call_id,
              )
              if (existing >= 0) {
                blocks[existing] = {
                  kind: 'templates',
                  toolCallId: event.tool_call_id,
                  templates: event.templates,
                }
              } else {
                blocks.push({
                  kind: 'templates',
                  toolCallId: event.tool_call_id,
                  templates: event.templates,
                })
              }
              return {
                ...last,
                blocks,
                templateSuggestions: {
                  ...(last.templateSuggestions ?? {}),
                  [event.tool_call_id]: event.templates,
                },
              }
            }),
          onApplicationPlan: (event) =>
            updateLast((last) => {
              const blocks = [...(last.blocks ?? [])]
              const existing = blocks.findIndex(
                (b) => b.kind === 'application_plan' && b.toolCallId === event.tool_call_id,
              )
              if (existing >= 0) {
                blocks[existing] = {
                  kind: 'application_plan',
                  toolCallId: event.tool_call_id,
                  plan: event.plan,
                }
              } else {
                blocks.push({
                  kind: 'application_plan',
                  toolCallId: event.tool_call_id,
                  plan: event.plan,
                })
              }
              return {
                ...last,
                blocks,
                applicationPlans: {
                  ...(last.applicationPlans ?? {}),
                  [event.tool_call_id]: event.plan,
                },
              }
            }),
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
              if (sid && !isAnonymous) {
                saveMessage(
                  sid,
                  'assistant',
                  finalMsg.content,
                  finalMsg.citations,
                  finalMsg.webSources,
                  finalMsg.artifacts,
                  finalMsg.compaction,
                  finalMsg.blocks,
                  finalMsg.toolCalls,
                )
              }
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

      // Update URL to session
      if (sid && !isAnonymous) {
        router.replace(`/chat/${sid}`, { scroll: false })
      }
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
  const isAnonymous = !user
  const displayName = user?.user_metadata?.full_name || user?.email?.split('@')[0] || 'Counsel'
  const greetingName = user ? displayName : 'there'

  return (
    <div className="flex flex-1 overflow-hidden" style={{ overscrollBehavior: 'none' }}>
      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        {!hasMessages ? (
          /* ── Welcome State ── */
          <div className="flex-1 flex flex-col items-center justify-center px-4 relative overflow-y-auto">
            {/* Subtle radial background */}
            <div
              className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[500px] h-[400px] pointer-events-none"
              style={{ background: 'radial-gradient(ellipse at center, rgba(34, 197, 94, 0.04) 0%, transparent 70%)' }}
            />

            <div className="text-center mb-8 space-y-4 relative z-10">
              {/* Levy logo, centered above the accent line */}
              <div className="flex justify-center mb-3">
                <LevyLogo size={56} className="opacity-90" />
              </div>

              {/* Emerald accent line - animates width */}
              <div
                className="mx-auto h-[2px] rounded-full bg-gradient-to-r from-transparent via-emerald-500/60 to-transparent mb-6 transition-all duration-1000 ease-out"
                style={{ width: `${accentLineWidth}px` }}
              />

              {/* Personalized greeting */}
              <h1
                className="text-3xl font-bold text-foreground tracking-tight"
                style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
              >
                {getGreeting()}, {greetingName}
              </h1>
              <p
                className="text-[15px] text-muted-foreground/60 italic"
                style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
              >
                Your counsel awaits
              </p>
              {isAnonymous && (
                <p className="text-[12px] text-white/35 max-w-md mx-auto pt-1">
                  Try a question. No account needed.
                  <Link
                    href="/auth/login"
                    className="ml-1 text-emerald-400/80 hover:text-emerald-400 underline decoration-emerald-500/30 underline-offset-2"
                  >
                    Sign in to save your chats
                  </Link>
                  .
                </p>
              )}
            </div>

            {/* Quick Action Cards - 2x2 grid on every viewport */}
            <div className="grid grid-cols-2 gap-2 sm:gap-2.5 mb-8 max-w-2xl w-full relative z-10">
              {quickActions.map((action, i) => (
                <button
                  key={i}
                  onClick={() => handleSend(action.description)}
                  className="flex flex-col sm:flex-row items-start gap-2 sm:gap-3 p-3 sm:p-4 rounded-xl text-left transition-all duration-200 group hover:scale-[1.01] active:scale-[0.99] border border-white/[0.06] bg-white/[0.02] hover:border-emerald-500/20 hover:bg-emerald-500/[0.04]"
                >
                  <action.icon className="w-4 h-4 sm:w-5 sm:h-5 text-white/20 group-hover:text-emerald-400/70 transition-colors flex-shrink-0 mt-0.5" />
                  <div className="min-w-0 w-full">
                    <div className="text-[12px] sm:text-[13px] font-medium text-white/60 group-hover:text-white/90 transition-colors leading-tight">
                      {action.label}
                    </div>
                    <div className="text-[10.5px] sm:text-[11px] text-white/30 group-hover:text-white/50 transition-colors mt-1 leading-snug line-clamp-2">
                      {action.description}
                    </div>
                  </div>
                </button>
              ))}
            </div>

            <div className="w-full max-w-3xl relative z-10">
              <ChatInput
                onSend={handleSend}
                disabled={loading}
                webSearch={webSearch}
                onWebSearchChange={setWebSearch}
                onAttachClick={user ? () => setAttachmentsOpen(true) : undefined}
                attachmentCount={stagedAttachments.length}
              />
            </div>

            <p className="mt-4 text-[10px] text-white/15 relative z-10 text-center">
              Levy provides legal information, not legal advice. Always consult a qualified lawyer.
            </p>
          </div>
        ) : (
          /* ── Chat State ── */
          <>
            <div
              className="flex-1 overflow-y-auto pt-6 pb-40 md:pb-32"
              style={{ overscrollBehavior: 'none' }}
            >
              <div className="max-w-3xl mx-auto space-y-6">
                {messages.map((msg, i) => {
                  const isLastAssistant =
                    loading && i === messages.length - 1 && msg.role === 'assistant'
                  const hasResearch = (msg.toolCalls?.length ?? 0) > 0
                  // Show ThinkingGlow only when nothing is happening yet -
                  // once the model has begun calling tools or streaming text,
                  // render the live ChatMessage so the user sees the research
                  // trail in real time.
                  const showGlow = isLastAssistant && !msg.content && !hasResearch
                  return (
                    <div key={i}>
                      {showGlow && <ThinkingGlow />}
                      {!showGlow && (
                        <ChatMessage
                          role={msg.role}
                          content={msg.content}
                          blocks={msg.blocks}
                          citations={msg.citations}
                          webSources={msg.webSources}
                          toolCalls={msg.toolCalls}
                          artifacts={msg.artifacts}
                          templateSuggestions={msg.templateSuggestions}
                          applicationPlans={msg.applicationPlans}
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
                          onUseTemplate={(t) =>
                            handleSend(
                              `Use my "${t.name}" template (id: ${t.id}) to draft this for me. Generate the document with pdf_generate using that template's structure as the basis.`,
                            )
                          }
                          onDraftBundle={(plan) =>
                            handleSend(
                              `Proceed with the plan. Draft the full application bundle for me: ${plan.documents_to_file.join(', ')}. Apply the heading and party block consistent with a Zambian ${plan.procedural_mode} in the ${plan.court_division}. Cause number is "[CAUSE NUMBER TO BE ALLOCATED]" unless I gave you one earlier.`,
                            )
                          }
                          onDraftIndividual={(plan, kind) => {
                            const map: Record<string, string> = {
                              summons: 'the Originating Notice of Motion / Summons',
                              affidavit: 'the Affidavit in Support',
                              skeletal: 'the Skeletal Arguments',
                              order: 'the Draft Order',
                            }
                            handleSend(
                              `Proceed with the plan. Draft ${map[kind]} only, using the Zambian ${plan.procedural_mode} format for the ${plan.court_division}. Cause number is "[CAUSE NUMBER TO BE ALLOCATED]" unless I gave you one earlier.`,
                            )
                          }}
                        />
                      )}
                    </div>
                  )
                })}
                <div ref={messagesEndRef} />
              </div>
            </div>
            {/* Floating glass dock - chat input */}
            <div className="absolute inset-x-0 bottom-0 z-20 pointer-events-none">
              <div
                className="px-3 sm:px-4 pt-6 pb-[max(12px,env(safe-area-inset-bottom))]"
                style={{
                  background:
                    'linear-gradient(to top, rgba(10,10,11,0.95) 0%, rgba(10,10,11,0.6) 60%, transparent 100%)',
                }}
              >
                <div className="pointer-events-auto max-w-3xl mx-auto">
                  {stagedAttachments.length > 0 && (
                    <div className="mb-2 flex flex-wrap gap-1.5 px-1">
                      {stagedAttachments.map((d) => (
                        <button
                          key={d.id}
                          type="button"
                          onClick={() =>
                            setStagedAttachments((prev) => prev.filter((x) => x.id !== d.id))
                          }
                          className="group flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-[11px] text-emerald-100/85 hover:bg-emerald-500/20"
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
                onAttachClick={user ? () => setAttachmentsOpen(true) : undefined}
                attachmentCount={stagedAttachments.length}
              />
                  <p className="mt-2 text-center text-[10px] text-white/25">
                    Levy provides legal information, not legal advice.
                  </p>
                </div>
              </div>
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

      <AttachmentsSheet
        open={attachmentsOpen}
        onClose={() => setAttachmentsOpen(false)}
        userId={user?.id}
        sessionId={sessionId}
        attachedIds={new Set(stagedAttachments.map((d) => d.id))}
        onToggle={async (doc) => {
          // If a session already exists, persist; otherwise stage locally.
          if (sessionId) {
            const isAttached = stagedAttachments.some((d) => d.id === doc.id)
            if (isAttached) {
              setStagedAttachments((prev) => prev.filter((d) => d.id !== doc.id))
              const { detachDocumentFromSession } = await import('@/lib/api')
              await detachDocumentFromSession(sessionId, doc.id)
            } else {
              setStagedAttachments((prev) => [...prev, doc])
              await attachDocumentToSession(sessionId, doc.id)
            }
          } else {
            setStagedAttachments((prev) =>
              prev.some((d) => d.id === doc.id)
                ? prev.filter((d) => d.id !== doc.id)
                : [...prev, doc],
            )
          }
        }}
      />
    </div>
  )
}
