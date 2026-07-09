'use client'

import { useState, useRef, useEffect, use } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/components/auth/auth-provider'
import { createClient } from '@/lib/supabase'
import { uploadDocument, promoteDocument } from '@/lib/api'
import { ChatInput } from '@/components/chat/chat-input'
import { ChatMessage, ThinkingGlow } from '@/components/chat/chat-message'
import { BriefPanel } from '@/components/chat/brief-panel'
import { useRegisterBrief } from '@/components/chat/brief-context'
import { useChatStream, type Message } from '@/components/chat/chat-stream-context'
import { usePdfViewer } from '@/components/chat/pdf-viewer-context'
import { useSessionAttachments } from '@/components/chat/use-session-attachments'
import { AttachmentsSheet } from '@/components/chat/attachments-sheet'
import type { ToolCallView } from '@/components/chat/tool-call-card'
import type { MessageBlock } from '@/components/chat/chat-message'
import { Loader2, Paperclip, X, ArrowUpToLine } from 'lucide-react'

const EMPTY_MESSAGES: Message[] = []

export default function ChatSessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const { user, session, loading: authLoading } = useAuth()
  const router = useRouter()
  const pdf = usePdfViewer()
  const attachments = useSessionAttachments(id)
  const { sessions, ensureLoaded, send } = useChatStream()

  const [webSearch, setWebSearch] = useState(false)
  const [attachmentsOpen, setAttachmentsOpen] = useState(false)
  // Save-to-Library promotion state (per chip).
  const [promoting, setPromoting] = useState<Set<string>>(new Set())
  const [promoted, setPromoted] = useState<Set<string>>(new Set())
  const [promotionSuggested, setPromotionSuggested] = useState<Set<string>>(new Set())

  const sess = sessions[id]
  const messages = sess?.messages ?? EMPTY_MESSAGES
  const loading = sess?.status === 'streaming'
  // While auth is resolving or the session hasn't been hydrated from the DB
  // yet, show the spinner. Once a session is present in the provider (loaded
  // or streaming), render its messages - even after navigating back mid-run.
  const initialLoading = authLoading || (!!user && !sess?.loaded)

  // Saved-thread routes require an account.
  useEffect(() => {
    if (!authLoading && !user) router.replace('/chat')
  }, [user, authLoading, router])

  useRegisterBrief(messages, session?.access_token)

  // Hydrate this session's history from the DB exactly once. The provider
  // guards against clobbering an in-flight stream, so navigating back to a
  // chat that's still generating keeps showing live progress.
  useEffect(() => {
    if (authLoading || !user) return
    ensureLoaded(id, () => loadMessagesFromDB(id))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, authLoading, user])

  // Auto-scroll only when already near the bottom.
  useEffect(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 140
    if (nearBottom) messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function handleSend(question: string) {
    // Snapshot the current attachments so the user message owns them. After
    // firing the stream we immediately detach them from the session, which
    // clears the chips and prevents the next turn from inheriting them.
    const pending = attachments.attached.map((d) => ({ id: d.id, title: d.title }))
    send(id, question, {
      token: session?.access_token,
      webSearch,
      userId: user?.id,
      attachedDocIds: pending.map((d) => d.id),
      attachedDocs: pending,
    })
    if (pending.length > 0) {
      // Fire-and-forget: the IDs are already in the in-flight streamQuery
      // body, so detaching now is safe.
      void Promise.all(pending.map((d) => attachments.detach(d.id)))
    }
  }

  // Upload-from-chat: ingest the file under this user, then attach it to the
  // current session. Skips the trip to the Documents page entirely.
  async function handleUploadFile(file: File) {
    if (!user) return
    const res = await uploadDocument(file, session?.access_token, user.id)
    if (res.suggest_promotion) {
      setPromotionSuggested((prev) => new Set(prev).add(res.document_id))
    }
    await attachments.attach(res.document_id)
  }

  // "Save to library" promotion — chunks + embeds the doc in place so it
  // becomes searchable across all the user's chats.
  async function handlePromote(docId: string) {
    setPromoting((prev) => new Set(prev).add(docId))
    try {
      await promoteDocument(docId, session?.access_token)
      setPromoted((prev) => new Set(prev).add(docId))
      setPromotionSuggested((prev) => {
        const n = new Set(prev)
        n.delete(docId)
        return n
      })
    } catch (err) {
      console.error('promote failed', err)
    } finally {
      setPromoting((prev) => {
        const n = new Set(prev)
        n.delete(docId)
        return n
      })
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
          ref={scrollContainerRef}
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
                      blocks={msg.blocks}
                      citations={msg.citations}
                      webSources={msg.webSources}
                      toolCalls={msg.toolCalls}
                      artifacts={msg.artifacts}
                      templateSuggestions={msg.templateSuggestions}
                      applicationPlans={msg.applicationPlans}
                      entitlementBreakdowns={msg.entitlementBreakdowns}
                      caseLaw={msg.caseLaw}
                      cheatSheets={msg.cheatSheets}
                      quizzes={msg.quizzes}
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
              {attachments.attached.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1.5 px-1">
                  {attachments.attached.map((d) => {
                    const isPromoting = promoting.has(d.id)
                    const isPromoted = promoted.has(d.id)
                    const suggested = promotionSuggested.has(d.id)
                    return (
                      <div
                        key={d.id}
                        className="group flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-900/90 border border-emerald-500/35 text-[11px] text-emerald-50"
                      >
                        <Paperclip size={10} className="text-emerald-300" />
                        <span className="max-w-[180px] truncate">{d.title}</span>
                        {!isPromoted && (
                          <button
                            type="button"
                            onClick={() => handlePromote(d.id)}
                            disabled={isPromoting}
                            title={
                              suggested
                                ? "You've used this file before — save it to your library for cross-chat search"
                                : 'Save to library for cross-chat search'
                            }
                            aria-label="Save to library"
                            className={`ml-0.5 ${
                              suggested
                                ? 'text-emerald-200 hover:text-white'
                                : 'text-emerald-300/70 hover:text-emerald-100'
                            } disabled:opacity-40`}
                          >
                            {isPromoting ? <Loader2 size={10} className="animate-spin" /> : <ArrowUpToLine size={10} />}
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => attachments.detach(d.id)}
                          aria-label={`Detach ${d.title}`}
                          className="text-emerald-300/60 hover:text-emerald-100"
                        >
                          <X size={10} />
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}
              <ChatInput
                onSend={handleSend}
                disabled={loading}
                webSearch={webSearch}
                onWebSearchChange={setWebSearch}
                onAttachClick={user ? () => setAttachmentsOpen(true) : undefined}
                onUploadFile={user ? handleUploadFile : undefined}
                attachmentCount={attachments.attached.length}
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
          <BriefPanel messages={messages.map((m) => ({ role: m.role, content: m.content }))} token={session?.access_token} />
        </aside>
      )}

      <AttachmentsSheet
        open={attachmentsOpen}
        onClose={() => setAttachmentsOpen(false)}
        userId={user?.id}
        sessionId={id}
        attachedIds={new Set(attachments.attachedIds)}
        onToggle={async (doc) => {
          const isAttached = attachments.attached.some((d) => d.id === doc.id)
          if (isAttached) await attachments.detach(doc.id)
          else await attachments.attach(doc.id)
        }}
      />
    </div>
  )
}

async function loadMessagesFromDB(id: string): Promise<Message[]> {
  const supabase = createClient()
  const { data } = await supabase
    .from('chat_messages')
    .select('role, content, blocks, tool_calls, citations, web_sources, artifacts, compaction')
    .eq('session_id', id)
    .order('created_at', { ascending: true })

  if (!data) return []
  return data.map((m) => ({
    role: m.role as 'user' | 'assistant',
    content: m.content,
    blocks: m.blocks as MessageBlock[] | undefined,
    toolCalls: m.tool_calls as ToolCallView[] | undefined,
    citations: m.citations as Message['citations'],
    webSources: m.web_sources as Message['webSources'],
    artifacts: m.artifacts as Message['artifacts'],
    compaction: m.compaction as Message['compaction'],
  }))
}
