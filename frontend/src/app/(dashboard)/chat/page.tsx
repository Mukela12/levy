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
import { useChatStream, type Message } from '@/components/chat/chat-stream-context'
import { usePdfViewer } from '@/components/chat/pdf-viewer-context'
import { AttachmentsSheet } from '@/components/chat/attachments-sheet'
import { attachDocumentToSession, promoteDocument, uploadDocument, type LibraryDocument } from '@/lib/api'
import {
  BookOpen,
  Search,
  Gavel,
  Paperclip,
  X,
  Loader2,
  ArrowUpToLine,
  TrendingUp,
  Globe,
  Leaf,
  Home,
  Banknote,
  FileSearch,
} from 'lucide-react'
import { LevyLogo } from '@/components/ui/levy-logo'

function getGreeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

// Eight practice areas, ordered by how often the test users actually
// reached for them. Each prompt is a single focused question so the
// agent answers it directly instead of unrolling a four-section essay.
const quickActions = [
  {
    icon: TrendingUp,
    label: 'Investment Law',
    description:
      'What is the minimum investment threshold for foreign investors in Zambia, and which incentives apply?',
  },
  {
    icon: Globe,
    label: 'International Law',
    description:
      'How are international treaties enforced in Zambian courts, and what jurisdiction applies to cross-border disputes?',
  },
  {
    icon: BookOpen,
    label: 'Company Registration',
    description:
      'What are the steps and forms required to register a private limited company with PACRA?',
  },
  {
    icon: Search,
    label: 'Employment Law',
    description:
      'What does Section 52 of the Employment Code Act require for a valid termination of employment?',
  },
  {
    icon: Gavel,
    label: 'Criminal Law',
    description:
      'What are the constitutional rights of an arrested person in Zambia?',
  },
  {
    icon: Banknote,
    label: 'Tax Law',
    description:
      'What are the current corporate income tax rates and turnover-tax thresholds in Zambia?',
  },
  {
    icon: Home,
    label: 'Property Law',
    description:
      'How is land tenure regulated under the Lands Act, and what is the procedure for converting customary land?',
  },
  {
    icon: Leaf,
    label: 'Environmental',
    description:
      'Which environmental impact assessment requirements apply to a mining operation in Zambia?',
  },
]

export default function NewChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [accentLineWidth, setAccentLineWidth] = useState(0)
  const [webSearch, setWebSearch] = useState(false)
  // Seed payload for the input box (used by the "Review my draft" starter,
  // which pre-fills a primer so the lawyer pastes their own text rather
  // than firing an empty turn).
  const [inputSeed, setInputSeed] = useState<{ text: string; nonce: number }>({
    text: '',
    nonce: 0,
  })
  // Staged attachments for the very first message: persisted into the
  // chat_session_documents join table once the session is created.
  const [stagedAttachments, setStagedAttachments] = useState<LibraryDocument[]>([])
  const [attachmentsOpen, setAttachmentsOpen] = useState(false)
  // Save-to-Library promotion state (per chip).
  const [promoting, setPromoting] = useState<Set<string>>(new Set())
  const [promoted, setPromoted] = useState<Set<string>>(new Set())
  const [promotionSuggested, setPromotionSuggested] = useState<Set<string>>(new Set())
  const pdf = usePdfViewer()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const { user, session, loading: authLoading } = useAuth()
  const router = useRouter()
  const { send } = useChatStream()
  const seededRef = useRef(false)

  // Expose the raw messages state (stable reference) to the layout-level
  // Brief button + bottom sheet. Do NOT map here - that creates a new array
  // every render and would loop with the provider's setState.
  useRegisterBrief(messages, session?.access_token)

  // Animate accent line on mount
  useEffect(() => {
    const timer = setTimeout(() => setAccentLineWidth(64), 100)
    return () => clearTimeout(timer)
  }, [])

  // Only auto-scroll when the user is already near the bottom, so a
  // streaming reply doesn't yank them down while they read from the top.
  useEffect(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 140
    if (nearBottom) messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Seeded prompt from /chat?q=... (Study launcher, Act pages, answer pages).
  // We PRE-FILL the composer and let the user press send. We must NOT auto-send:
  // search crawlers render this page when they follow the many /chat?q= links,
  // and an auto-send would fire a full (billed) agent run on every crawl.
  useEffect(() => {
    if (seededRef.current) return
    const q = new URLSearchParams(window.location.search).get('q')
    if (!q) return
    seededRef.current = true
    window.history.replaceState(null, '', '/chat')
    setInputSeed({ text: q, nonce: Date.now() })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Upload-from-chat on the new-chat page: ingest the file into the user's
  // library now (so we have a document_id), then stage it locally. On send,
  // the staged doc is pinned to the user message and the session never
  // session-attaches it (per-message scoping).
  async function handleUploadFile(file: File) {
    if (!user) return
    const res = await uploadDocument(file, session?.access_token, user.id)
    if (res.suggest_promotion) {
      setPromotionSuggested((prev) => new Set(prev).add(res.document_id))
    }
    setStagedAttachments((prev) => [
      ...prev,
      { id: res.document_id, title: file.name, is_global: false } as LibraryDocument,
    ])
  }

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

  async function handleSend(question: string) {
    // Signed-in: hand the stream to the shared provider so it keeps running
    // even if the user switches chats, then move to the saved-thread route.
    if (user) {
      setLoading(true)
      // Optimistic display so the welcome screen doesn't linger during the
      // route transition; the [id] page re-renders from the provider on mount.
      setMessages([
        { role: 'user', content: question },
        { role: 'assistant', content: '', blocks: [] },
      ])
      try {
        const sid = sessionId ?? (await createSession(question))
        if (!sessionId) setSessionId(sid)
        const pending = stagedAttachments.map((d) => ({ id: d.id, title: d.title }))
        // Skip attachDocumentToSession on purpose: with per-message scoping the
        // doc is passed as attached_doc_ids on this turn only, and pinned to
        // the user message via the attachments block. Session-level attachment
        // is what caused chips to bleed into subsequent turns.
        send(sid, question, {
          token: session?.access_token,
          webSearch,
          userId: user.id,
          attachedDocIds: pending.map((d) => d.id),
          attachedDocs: pending,
        })
        setStagedAttachments([])
        router.replace(`/chat/${sid}`, { scroll: false })
      } catch (e) {
        const content =
          e instanceof Error && !e.message.startsWith('API error') && !e.message.startsWith('No response')
            ? e.message
            : 'Sorry, I encountered an error processing your question. Please try again.'
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          const errorMsg: Message = {
            role: 'assistant',
            content,
          }
          if (last && last.role === 'assistant' && last.content === '') {
            return [...prev.slice(0, -1), errorMsg]
          }
          return [...prev, errorMsg]
        })
        setLoading(false)
      }
      return
    }

    // Anonymous: keep everything in React state, never touch the DB.
    setLoading(true)
    setMessages((prev) => [...prev, { role: 'user', content: question }])

    try {
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

      const history = messages
        .filter((m) => m.content)
        .map((m) => ({ role: m.role, content: m.content }))

      await streamQuery(
        question,
        { token: session?.access_token, webSearch, history },
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
          onEntitlementBreakdown: (event) =>
            updateLast((last) => {
              const blocks = [...(last.blocks ?? [])]
              const existing = blocks.findIndex(
                (b) => b.kind === 'entitlement' && b.toolCallId === event.tool_call_id,
              )
              const block = {
                kind: 'entitlement' as const,
                toolCallId: event.tool_call_id,
                breakdown: event.breakdown,
              }
              if (existing >= 0) blocks[existing] = block
              else blocks.push(block)
              return {
                ...last,
                blocks,
                entitlementBreakdowns: {
                  ...(last.entitlementBreakdowns ?? {}),
                  [event.tool_call_id]: event.breakdown,
                },
              }
            }),
          onCaseLaw: (event) =>
            updateLast((last) => {
              const blocks = [...(last.blocks ?? [])]
              const existing = blocks.findIndex(
                (b) => b.kind === 'case_law' && b.toolCallId === event.tool_call_id,
              )
              const block = {
                kind: 'case_law' as const,
                toolCallId: event.tool_call_id,
                cases: event.cases,
              }
              if (existing >= 0) blocks[existing] = block
              else blocks.push(block)
              return {
                ...last,
                blocks,
                caseLaw: {
                  ...(last.caseLaw ?? {}),
                  [event.tool_call_id]: event.cases,
                },
              }
            }),
          onCheatSheet: (event) =>
            updateLast((last) => {
              const blocks = [...(last.blocks ?? [])]
              const existing = blocks.findIndex(
                (b) => b.kind === 'cheat_sheet' && b.toolCallId === event.tool_call_id,
              )
              const block = {
                kind: 'cheat_sheet' as const,
                toolCallId: event.tool_call_id,
                cheatSheet: event.cheat_sheet,
              }
              if (existing >= 0) blocks[existing] = block
              else blocks.push(block)
              return {
                ...last,
                blocks,
                cheatSheets: {
                  ...(last.cheatSheets ?? {}),
                  [event.tool_call_id]: event.cheat_sheet,
                },
              }
            }),
          onQuiz: (event) =>
            updateLast((last) => {
              const blocks = [...(last.blocks ?? [])]
              const existing = blocks.findIndex(
                (b) => b.kind === 'quiz' && b.toolCallId === event.tool_call_id,
              )
              const block = {
                kind: 'quiz' as const,
                toolCallId: event.tool_call_id,
                quiz: event.quiz,
              }
              if (existing >= 0) blocks[existing] = block
              else blocks.push(block)
              return {
                ...last,
                blocks,
                quizzes: {
                  ...(last.quizzes ?? {}),
                  [event.tool_call_id]: event.quiz,
                },
              }
            }),
          onDone: (metadata) => {
            updateLast((last) => ({
              ...last,
              citations: metadata.chunks_used,
              webSources: metadata.web_sources,
              timing: { total_ms: metadata.timing?.total_ms ?? 0 },
            }))
            setLoading(false)
          },
          onError: (msg) =>
            updateLast((last) => ({
              ...last,
              content:
                (last.content || '') + (last.content ? '\n\n' : '') + `_Error: ${msg}_`,
            })),
        },
      )
    } catch (e) {
      const errorMsg: Message = {
        role: 'assistant',
        content:
          e instanceof Error && !e.message.startsWith('API error') && !e.message.startsWith('No response')
            ? e.message
            : 'Sorry, I encountered an error processing your question. Please try again.',
      }
      setMessages((prev) => {
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
          <div
            className="flex-1 flex flex-col items-center px-4 relative overflow-y-auto overscroll-none"
            style={{ overscrollBehavior: 'none' }}
          >
            {/* Subtle radial background */}
            <div
              className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[500px] h-[400px] pointer-events-none"
              style={{ background: 'radial-gradient(ellipse at center, rgba(34, 197, 94, 0.04) 0%, transparent 70%)' }}
            />

            {/* Centering wrapper: my-auto centers the content when it fits the
                viewport and collapses to a clean top-aligned scroll when it
                overflows on short phones — so the greeting never clips and the
                screen no longer rubber-bands. */}
            <div className="w-full flex flex-col items-center my-auto">

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

            {/* Practice-area starter cards. Eight areas in 2 columns on
                mobile / 4 on desktop. Each card shows the area label only
                — the long descriptions live on hover (title tooltip) so
                the grid feels calm at first glance and only reveals the
                example question when the user actually points at one. */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-2.5 mb-3 max-w-3xl w-full relative z-10">
              {quickActions.map((action, i) => (
                <button
                  key={i}
                  onClick={() => handleSend(action.description)}
                  title={action.description}
                  className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-left transition-colors duration-150 group border border-white/[0.06] bg-white/[0.02] hover:border-emerald-500/20 hover:bg-emerald-500/[0.04]"
                >
                  <action.icon className="w-4 h-4 text-white/25 group-hover:text-emerald-400/70 transition-colors flex-shrink-0" />
                  <span className="text-[12px] font-medium text-white/60 group-hover:text-white/90 transition-colors truncate">
                    {action.label}
                  </span>
                </button>
              ))}
            </div>

            {/* Review-my-work starter — distinct from the Q&A cards because it
                pre-fills the box with a primer and lets the lawyer paste their
                own draft (the "criticise my work / find gaps" workflow). */}
            <button
              onClick={() =>
                setInputSeed((s) => ({
                  text:
                    'Please review the following draft and give me a candid critique — ' +
                    'strengths, gaps and missing provisions, any enforceability or legal ' +
                    'issues (with citations to Zambian law), and language/style fixes. ' +
                    'Then offer to produce a clean revised version.\n\n--- MY DRAFT ---\n',
                  nonce: s.nonce + 1,
                }))
              }
              className="mb-6 max-w-3xl w-full flex items-center gap-2.5 px-3.5 py-3 rounded-lg text-left transition-colors duration-150 group border border-emerald-500/20 bg-emerald-500/[0.04] hover:border-emerald-500/35 hover:bg-emerald-500/[0.07] relative z-10"
            >
              <FileSearch className="w-4 h-4 text-emerald-400/70 flex-shrink-0" />
              <span className="flex-1 min-w-0">
                <span className="block text-[12.5px] font-medium text-white/85">
                  Review my draft
                </span>
                <span className="block text-[11px] text-white/40 truncate">
                  Paste a contract, affidavit or submission. Levy critiques it and finds gaps.
                </span>
              </span>
            </button>

            <div className="w-full max-w-3xl relative z-10">
              <ChatInput
                onSend={handleSend}
                disabled={loading}
                webSearch={webSearch}
                onWebSearchChange={setWebSearch}
                onAttachClick={user ? () => setAttachmentsOpen(true) : undefined}
                onUploadFile={user ? handleUploadFile : undefined}
                attachmentCount={stagedAttachments.length}
                seed={inputSeed}
              />
            </div>

            {/* Breadth cue — the curated library is far bigger than the eight
                cards suggest; lawyers told us it "felt limited to four areas". */}
            <Link
              href="/documents"
              className="mt-4 text-[11.5px] text-white/35 hover:text-emerald-400/80 transition-colors relative z-10"
            >
              Browse 190+ Zambian Acts, forms &amp; government documents →
            </Link>

            <p className="mt-4 text-[10px] text-white/15 relative z-10 text-center">
              Levy provides legal information, not legal advice. Always consult a qualified lawyer.
            </p>
            </div>
          </div>
        ) : (
          /* ── Chat State ── */
          <>
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
                  {stagedAttachments.length > 0 && (
                    <div className="mb-2 flex flex-wrap gap-1.5 px-1">
                      {stagedAttachments.map((d) => {
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
                              onClick={() =>
                                setStagedAttachments((prev) => prev.filter((x) => x.id !== d.id))
                              }
                              aria-label={`Remove ${d.title}`}
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
