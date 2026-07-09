'use client'

import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import { createClient } from '@/lib/supabase'
import { streamQuery } from '@/lib/api'
import type { ToolCallView } from '@/components/chat/tool-call-card'
import type { MessageBlock } from '@/components/chat/chat-message'
import type {
  ApplicationPlan,
  ArtifactView,
  CaseLawMatch,
  CheatSheet,
  ChunkUsed,
  EntitlementBreakdown,
  Quiz,
  TemplateSuggestion,
  WebSource,
} from '@/lib/api'

export interface Message {
  role: 'user' | 'assistant'
  content: string
  blocks?: MessageBlock[]
  citations?: ChunkUsed[]
  webSources?: WebSource[]
  toolCalls?: ToolCallView[]
  artifacts?: ArtifactView[]
  templateSuggestions?: Record<string, TemplateSuggestion[]>
  applicationPlans?: Record<string, ApplicationPlan>
  entitlementBreakdowns?: Record<string, EntitlementBreakdown>
  caseLaw?: Record<string, CaseLawMatch[]>
  cheatSheets?: Record<string, CheatSheet>
  quizzes?: Record<string, Quiz>
  timing?: { total_ms: number }
  compaction?: { summarised_messages: number; tokens_before: number; tokens_after: number }
}

export interface SessionState {
  messages: Message[]
  status: 'idle' | 'streaming' | 'error'
  loaded: boolean
}

export interface SendOptions {
  token?: string
  webSearch?: boolean
  userId?: string
  attachedDocIds?: string[]
  /**
   * Display metadata for the attached docs (id + title), pinned to the user
   * message via a 'attachments' block so the chip remains visible on the
   * sent turn and the attachment is scoped to that single message.
   */
  attachedDocs?: Array<{ id: string; title: string }>
}

interface ChatStreamContextValue {
  sessions: Record<string, SessionState>
  streamingIds: string[]
  isStreaming: (sessionId: string) => boolean
  ensureLoaded: (sessionId: string, loader: () => Promise<Message[]>) => void
  send: (sessionId: string, question: string, opts: SendOptions) => void
}

const ChatStreamContext = createContext<ChatStreamContextValue | null>(null)

const EMPTY_SESSION: SessionState = { messages: [], status: 'idle', loaded: false }

async function saveMessage(sid: string, role: string, m: Partial<Message>) {
  const supabase = createClient()
  await supabase.from('chat_messages').insert({
    session_id: sid,
    role,
    content: m.content ?? '',
    blocks: m.blocks ?? null,
    tool_calls: m.toolCalls ?? null,
    citations: m.citations ?? null,
    web_sources: m.webSources ?? null,
    artifacts: m.artifacts ?? null,
    compaction: m.compaction ?? null,
  })
}

export function ChatStreamProvider({ children }: { children: React.ReactNode }) {
  const [sessions, setSessions] = useState<Record<string, SessionState>>({})
  // A synchronous mirror of `sessions` so event handlers can read the latest
  // committed state without waiting for a re-render. Every mutation flows
  // through `commit`, which updates both the state and this ref.
  const sessionsRef = useRef<Record<string, SessionState>>({})
  const loadingRef = useRef<Set<string>>(new Set())

  const commit = useCallback(
    (updater: (prev: Record<string, SessionState>) => Record<string, SessionState>) => {
      setSessions((prev) => {
        const next = updater(prev)
        sessionsRef.current = next
        return next
      })
    },
    [],
  )

  const updateLast = useCallback(
    (sid: string, patch: (m: Message) => Message) => {
      commit((prev) => {
        const cur = prev[sid]
        if (!cur || cur.messages.length === 0) return prev
        const msgs = [...cur.messages]
        msgs[msgs.length - 1] = patch(msgs[msgs.length - 1])
        return { ...prev, [sid]: { ...cur, messages: msgs } }
      })
    },
    [commit],
  )

  const ensureLoaded = useCallback(
    (sid: string, loader: () => Promise<Message[]>) => {
      const cur = sessionsRef.current[sid]
      if (cur?.loaded || loadingRef.current.has(sid)) return
      loadingRef.current.add(sid)
      loader()
        .then((messages) => {
          loadingRef.current.delete(sid)
          commit((prev) => {
            const c = prev[sid]
            // A send may have populated/streamed into this session while the
            // DB read was in flight - never clobber live state.
            if (c?.loaded) return prev
            return { ...prev, [sid]: { messages, status: c?.status ?? 'idle', loaded: true } }
          })
        })
        .catch(() => {
          loadingRef.current.delete(sid)
        })
    },
    [commit],
  )

  const send = useCallback(
    (sid: string, question: string, opts: SendOptions) => {
      const cur = sessionsRef.current[sid] ?? EMPTY_SESSION
      const history = cur.messages
        .filter((m) => m.content)
        .map((m) => ({ role: m.role, content: m.content }))

      const userMsg: Message = {
        role: 'user',
        content: question,
        // Pin the attachment list onto this specific user message via a
        // dedicated block kind. Persisted with the message and rendered as
        // a chip above the bubble on reload.
        ...(opts.attachedDocs && opts.attachedDocs.length > 0
          ? { blocks: [{ kind: 'attachments', docs: opts.attachedDocs }] }
          : {}),
      }
      const assistantMsg: Message = {
        role: 'assistant',
        content: '',
        blocks: [],
        citations: [],
        toolCalls: [],
        artifacts: [],
      }

      commit((prev) => {
        const c = prev[sid] ?? EMPTY_SESSION
        return {
          ...prev,
          [sid]: {
            loaded: true,
            status: 'streaming',
            messages: [...c.messages, userMsg, assistantMsg],
          },
        }
      })

      // Persist the user turn (fire-and-forget; streaming proceeds regardless).
      void saveMessage(sid, 'user', userMsg)

      streamQuery(
        question,
        {
          token: opts.token,
          webSearch: opts.webSearch,
          userId: opts.userId,
          sessionId: sid,
          attachedDocIds: opts.attachedDocIds,
          history,
        },
        undefined,
        undefined,
        {
          onToken: (chunk) =>
            updateLast(sid, (last) => {
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
            updateLast(sid, (last) => ({
              ...last,
              blocks: [...(last.blocks ?? []), { kind: 'tool', toolCallId: call.id }],
              toolCalls: [...(last.toolCalls ?? []), { ...call, status: 'running', db: [], web: [] }],
            })),
          onToolResult: (result) =>
            updateLast(sid, (last) => ({
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
            updateLast(sid, (last) => {
              const existing = last.artifacts ?? []
              if (existing.some((a) => a.id === artifact.id)) return last
              return { ...last, artifacts: [...existing, artifact] }
            }),
          onCompaction: (info) =>
            updateLast(sid, (last) => ({
              ...last,
              compaction: {
                summarised_messages: info.summarised_messages,
                tokens_before: info.tokens_before,
                tokens_after: info.tokens_after,
              },
            })),
          onTemplateSuggestion: (event) =>
            updateLast(sid, (last) => {
              const blocks = [...(last.blocks ?? [])]
              const existing = blocks.findIndex(
                (b) => b.kind === 'templates' && b.toolCallId === event.tool_call_id,
              )
              const block: MessageBlock = {
                kind: 'templates',
                toolCallId: event.tool_call_id,
                templates: event.templates,
              }
              if (existing >= 0) blocks[existing] = block
              else blocks.push(block)
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
            updateLast(sid, (last) => {
              const blocks = [...(last.blocks ?? [])]
              const existing = blocks.findIndex(
                (b) => b.kind === 'application_plan' && b.toolCallId === event.tool_call_id,
              )
              const block: MessageBlock = {
                kind: 'application_plan',
                toolCallId: event.tool_call_id,
                plan: event.plan,
              }
              if (existing >= 0) blocks[existing] = block
              else blocks.push(block)
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
            updateLast(sid, (last) => {
              const blocks = [...(last.blocks ?? [])]
              const existing = blocks.findIndex(
                (b) => b.kind === 'entitlement' && b.toolCallId === event.tool_call_id,
              )
              const block: MessageBlock = {
                kind: 'entitlement',
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
            updateLast(sid, (last) => {
              const blocks = [...(last.blocks ?? [])]
              const existing = blocks.findIndex(
                (b) => b.kind === 'case_law' && b.toolCallId === event.tool_call_id,
              )
              const block: MessageBlock = {
                kind: 'case_law',
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
            updateLast(sid, (last) => {
              const blocks = [...(last.blocks ?? [])]
              const existing = blocks.findIndex(
                (b) => b.kind === 'cheat_sheet' && b.toolCallId === event.tool_call_id,
              )
              const block: MessageBlock = {
                kind: 'cheat_sheet',
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
            updateLast(sid, (last) => {
              const blocks = [...(last.blocks ?? [])]
              const existing = blocks.findIndex(
                (b) => b.kind === 'quiz' && b.toolCallId === event.tool_call_id,
              )
              const block: MessageBlock = {
                kind: 'quiz',
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
            let finalMsg: Message | null = null
            commit((prev) => {
              const c = prev[sid]
              if (!c || c.messages.length === 0) return prev
              const msgs = [...c.messages]
              const last = msgs[msgs.length - 1]
              finalMsg = {
                ...last,
                citations: metadata.chunks_used,
                webSources: metadata.web_sources,
                timing: { total_ms: metadata.timing?.total_ms ?? 0 },
              }
              msgs[msgs.length - 1] = finalMsg
              return { ...prev, [sid]: { ...c, status: 'idle', messages: msgs } }
            })
            // The assistant message is now persisted SERVER-SIDE (durable run),
            // so it saves even if this tab closed mid-stream. Do not insert it
            // here too, or reloads would show a duplicate reply.
          },
          onError: (msg) =>
            updateLast(sid, (last) => ({
              ...last,
              content: (last.content || '') + (last.content ? '\n\n' : '') + `_Error: ${msg}_`,
            })),
        },
      ).catch((e) => {
        const friendly =
          e instanceof Error && !e.message.startsWith('API error') && !e.message.startsWith('No response')
            ? e.message
            : 'Sorry, I encountered an error. Please try again.'
        commit((prev) => {
          const c = prev[sid]
          if (!c || c.messages.length === 0) return prev
          const msgs = [...c.messages]
          const last = msgs[msgs.length - 1]
          if (last.role === 'assistant' && !last.content) {
            msgs[msgs.length - 1] = {
              ...last,
              content: friendly,
            }
          }
          return { ...prev, [sid]: { ...c, status: 'error', messages: msgs } }
        })
      })
    },
    [commit, updateLast],
  )

  const streamingIds = useMemo(
    () => Object.keys(sessions).filter((id) => sessions[id].status === 'streaming'),
    [sessions],
  )

  const isStreaming = useCallback(
    (sid: string) => sessionsRef.current[sid]?.status === 'streaming',
    [],
  )

  const value = useMemo<ChatStreamContextValue>(
    () => ({ sessions, streamingIds, isStreaming, ensureLoaded, send }),
    [sessions, streamingIds, isStreaming, ensureLoaded, send],
  )

  return <ChatStreamContext.Provider value={value}>{children}</ChatStreamContext.Provider>
}

export function useChatStream() {
  const ctx = useContext(ChatStreamContext)
  if (!ctx) throw new Error('useChatStream must be used within ChatStreamProvider')
  return ctx
}
