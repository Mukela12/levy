'use client'

import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ChevronDown, ChevronUp, FileText, Clock, Scale, Globe, ExternalLink, Paperclip } from 'lucide-react'
import { MatchBadge } from '@/components/ui/match-badge'
import { TextShimmer } from '@/components/ui/text-shimmer'
import { ToolCallCard, type ToolCallView } from './tool-call-card'
import { AgentTask } from './agent-task'
import { ArtifactCard } from './artifact-card'
import { Favicon } from './favicon'
import { TemplateSuggestions } from './template-suggestions'
import { ApplicationPlanCard } from './application-plan-card'
import { EntitlementCard } from './entitlement-card'
import { PrecedentCard } from './precedent-card'
import { CheatSheetCard } from './cheat-sheet-card'
import { QuizCard } from './quiz-card'
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

/**
 * A chronological "block" - either a chunk of streamed prose or a reference
 * to a tool call by id. We render blocks in order so tool-call cards appear
 * inline at the moment they fire (Claude Code / Codex style) rather than
 * stacked above the answer.
 */
export type MessageBlock =
  | { kind: 'text'; text: string }
  | { kind: 'tool'; toolCallId: string }
  | { kind: 'templates'; toolCallId: string; templates?: TemplateSuggestion[] }
  | { kind: 'application_plan'; toolCallId: string; plan?: ApplicationPlan }
  | { kind: 'entitlement'; toolCallId: string; breakdown?: EntitlementBreakdown }
  | { kind: 'case_law'; toolCallId: string; cases?: CaseLawMatch[] }
  | { kind: 'cheat_sheet'; toolCallId: string; cheatSheet?: CheatSheet }
  | { kind: 'quiz'; toolCallId: string; quiz?: Quiz }
  // Captures which library docs the user attached to this specific turn. We
  // store it on the user message so attachments are scoped to one message
  // (not the whole session) and remain visible in the chat history.
  | { kind: 'attachments'; docs: Array<{ id: string; title: string }> }

interface ChatMessageProps {
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
  isStreaming?: boolean
  compaction?: { summarised_messages: number; tokens_before: number; tokens_after: number }
  onOpenCitation?: (cite: ChunkUsed) => void
  onOpenArtifact?: (artifact: ArtifactView) => void
  onUseTemplate?: (template: TemplateSuggestion) => void
  onDraftBundle?: (plan: ApplicationPlan) => void
  onDraftIndividual?: (plan: ApplicationPlan, kind: 'summons' | 'affidavit' | 'skeletal' | 'order') => void
}

export function ChatMessage({
  role,
  content,
  blocks,
  citations,
  webSources,
  toolCalls,
  artifacts,
  templateSuggestions,
  applicationPlans,
  entitlementBreakdowns,
  caseLaw,
  cheatSheets,
  quizzes,
  timing,
  isStreaming,
  compaction,
  onOpenCitation,
  onOpenArtifact,
  onUseTemplate,
  onDraftBundle,
  onDraftIndividual,
}: ChatMessageProps) {
  const [showCitations, setShowCitations] = useState(false)
  const [showWebSources, setShowWebSources] = useState(false)

  if (role === 'user') {
    const attachBlock = blocks?.find(
      (b): b is Extract<MessageBlock, { kind: 'attachments' }> => b.kind === 'attachments',
    )
    const attachedDocs = attachBlock?.docs ?? []
    return (
      <div className="flex justify-end px-4 md:px-0">
        <div className="max-w-[78%] md:max-w-[70%]">
          {/* Per-message attachment chips. Pinned above the bubble so the user
              can see exactly which document(s) Levy was asked to read for this
              turn. Opaque emerald so the page bg doesn't bleed through. */}
          {attachedDocs.length > 0 && (
            <div className="mb-1.5 flex flex-wrap justify-end gap-1.5">
              {attachedDocs.map((d) => (
                <span
                  key={d.id}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-900/90 border border-emerald-500/35 text-[11px] text-emerald-50"
                >
                  <Paperclip size={10} className="text-emerald-300" />
                  <span className="max-w-[180px] truncate">{d.title}</span>
                </span>
              ))}
            </div>
          )}
          <div
            className="px-5 py-3.5 text-[14px] leading-relaxed text-white/90 rounded-2xl"
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
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-3 px-4 md:px-0">
      <div className="flex-1 min-w-0 space-y-2.5">
        {/* Compaction notice - appears once, only on the assistant turn that
            triggered compaction. The Brief panel still has the full transcript. */}
        {compaction && (
          <div className="rounded-lg border border-emerald-500/15 bg-emerald-500/[0.04] px-3 py-2 text-[11px] text-emerald-300/80 flex items-center gap-2">
            <Scale className="size-3 text-emerald-400/70" />
            <span>
              Earlier conversation summarised to keep the thread within context
              ({compaction.summarised_messages} messages compressed,{' '}
              {Math.round((compaction.tokens_before - compaction.tokens_after) / 1000)}K tokens reclaimed).
              Full transcript preserved in the Brief.
            </span>
          </div>
        )}

        {/* AI Card Container */}
        <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] border-l-[3px] border-l-emerald-500/40 px-4 py-4">
          {/* AI Avatar Header */}
          <div className="flex items-center gap-2 mb-3">
            <div className="w-6 h-6 rounded-full bg-emerald-500/10 flex items-center justify-center">
              <Scale className="w-3 h-3 text-emerald-400" />
            </div>
            <span
              className="text-[11px] font-medium text-white/30 tracking-wide uppercase"
              style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
            >
              Levy AI
            </span>
          </div>

          {/* Content - Claude-Code/Codex style: tool-call cards interleave
              chronologically with prose segments, so the user sees research
              happen in real time. Legacy messages without `blocks` fall back
              to a single text block + tool cards stacked above. */}
          <div className="text-[14px] leading-[1.7] text-white/75 [&_h2]:text-white/90 [&_h2]:text-[14.5px] [&_h2]:font-semibold [&_h2]:mt-4 [&_h2]:mb-1.5 [&_strong]:text-white/85 [&_li]:text-white/70 [&_li]:mb-1 [&_code]:text-emerald-400/70 [&_code]:bg-white/[0.04] [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-[12.5px] [&_p]:mb-2">
            {blocks && blocks.length > 0 ? (
              blocks.map((block, idx) => {
                if (block.kind === 'text') {
                  if (!block.text) return null
                  const isLastBlock = idx === blocks.length - 1
                  return (
                    <div key={`t-${idx}`}>
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.text}</ReactMarkdown>
                      {isStreaming && isLastBlock && (
                        <span className="inline-block w-px h-3.5 bg-white/40 animate-pulse ml-0.5" />
                      )}
                    </div>
                  )
                }
                if (block.kind === 'templates') {
                  const suggestions =
                    block.templates ??
                    templateSuggestions?.[block.toolCallId] ??
                    []
                  if (suggestions.length === 0) return null
                  return (
                    <TemplateSuggestions
                      key={`ts-${block.toolCallId}`}
                      templates={suggestions}
                      onUseTemplate={(t) => onUseTemplate?.(t)}
                    />
                  )
                }
                if (block.kind === 'application_plan') {
                  const plan = block.plan ?? applicationPlans?.[block.toolCallId]
                  if (!plan) return null
                  return (
                    <ApplicationPlanCard
                      key={`ap-${block.toolCallId}`}
                      plan={plan}
                      onDraftBundle={onDraftBundle ? () => onDraftBundle(plan) : undefined}
                      onDraftIndividual={
                        onDraftIndividual
                          ? (kind) => onDraftIndividual(plan, kind)
                          : undefined
                      }
                    />
                  )
                }
                if (block.kind === 'entitlement') {
                  const breakdown = block.breakdown ?? entitlementBreakdowns?.[block.toolCallId]
                  if (!breakdown) return null
                  return <EntitlementCard key={`ent-${block.toolCallId}`} breakdown={breakdown} />
                }
                if (block.kind === 'case_law') {
                  const cases = block.cases ?? caseLaw?.[block.toolCallId]
                  if (!cases?.length) return null
                  return (
                    <PrecedentCard
                      key={`law-${block.toolCallId}`}
                      cases={cases}
                      onOpenCase={(documentId, title) =>
                        onOpenCitation?.({ document_id: documentId, act_name: title, page_start: 1 } as ChunkUsed)
                      }
                    />
                  )
                }
                if (block.kind === 'cheat_sheet') {
                  const sheet = block.cheatSheet ?? cheatSheets?.[block.toolCallId]
                  if (!sheet) return null
                  return <CheatSheetCard key={`cs-${block.toolCallId}`} sheet={sheet} />
                }
                if (block.kind === 'quiz') {
                  const quiz = block.quiz ?? quizzes?.[block.toolCallId]
                  if (!quiz?.questions?.length) return null
                  return <QuizCard key={`quiz-${block.toolCallId}`} quiz={quiz} />
                }
                // The 'attachments' block only ever appears on user messages
                // (it's the chip listing what the user attached for that
                // turn). Skip it in the assistant render path.
                if (block.kind === 'attachments') return null
                const call = (toolCalls || []).find((c) => c.id === block.toolCallId)
                if (!call) {
                  // Older saved messages may have block refs without the
                  // matching toolCalls payload. Render a compact stub so the
                  // chronological structure is preserved instead of dropping
                  // the block silently.
                  return (
                    <div
                      key={`tc-stub-${block.toolCallId}`}
                      className="my-2.5 -mx-1 rounded-lg border border-white/[0.06] bg-white/[0.015] px-3 py-2 flex items-center gap-2 text-[11.5px] text-white/40"
                    >
                      <span className="size-1.5 rounded-full bg-emerald-400/40 inline-block" />
                      Tool call (history)
                    </div>
                  )
                }
                return (
                  <div key={`tc-${block.toolCallId}`} className="my-2.5 -mx-1">
                    <AgentTask call={call} />
                  </div>
                )
              })
            ) : (
              <>
                {/* Legacy fallback: tool cards above, then full content */}
                {toolCalls && toolCalls.length > 0 && (
                  <div className="space-y-1.5 mb-3 -mx-1">
                    {toolCalls.map((call) => (
                      <ToolCallCard key={call.id} call={call} />
                    ))}
                  </div>
                )}
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
                {isStreaming && content && (
                  <span className="inline-block w-px h-3.5 bg-white/40 animate-pulse ml-0.5" />
                )}
              </>
            )}
            {/* Three-dot pulse before any block has arrived */}
            {isStreaming && !content && (!blocks || blocks.length === 0) && (
              <div className="flex items-center gap-1 py-2">
                <span className="w-1 h-1 rounded-full bg-white/30 animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1 h-1 rounded-full bg-white/30 animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1 h-1 rounded-full bg-white/30 animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            )}
            {/* Gap shimmer: streaming, but the model is composing the next step
                (e.g. writing quiz questions) so no token is printing and no tool
                card is spinning. Without this the UI looks frozen between cards. */}
            {isStreaming && blocks && blocks.length > 0 && (() => {
              const last = blocks[blocks.length - 1]
              const toolRunning = (toolCalls || []).some((c) => c.status === 'running')
              if (toolRunning || !last || last.kind === 'text') return null
              return (
                <div className="flex items-center gap-2 py-2">
                  <span className="relative flex size-2">
                    <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400/50 animate-ping" />
                    <span className="relative inline-flex size-2 rounded-full bg-emerald-400/70" />
                  </span>
                  <TextShimmer as="span" duration={1.6} className="text-[12.5px]">Working…</TextShimmer>
                </div>
              )
            })()}
          </div>
        </div>

        {/* Artifacts (generated/extracted/merged PDFs) */}
        {artifacts && artifacts.length > 0 && (
          <div className="space-y-2 pt-1">
            {artifacts.map((art) => (
              <ArtifactCard key={art.id} artifact={art} onOpen={() => onOpenArtifact?.(art)} />
            ))}
          </div>
        )}

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
                  <button
                    key={cite.id || i}
                    type="button"
                    onClick={() => onOpenCitation?.(cite)}
                    className="w-full text-left px-3.5 py-3 rounded-lg bg-white/[0.02] border border-white/[0.05] space-y-1.5 hover:border-emerald-500/25 hover:bg-emerald-500/[0.025] transition-colors group"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-[12px] font-semibold text-emerald-400/80 group-hover:text-emerald-400 truncate transition-colors">
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
                      <p className="text-[10px] text-white/15 group-hover:text-emerald-400/40 transition-colors">
                        Open at p.{cite.page_start}{cite.page_end && cite.page_end !== cite.page_start ? `–${cite.page_end}` : ''} →
                      </p>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Web sources */}
        {webSources && webSources.length > 0 && (
          <div className="space-y-2 pt-1">
            <button
              onClick={() => setShowWebSources(!showWebSources)}
              className="flex items-center gap-1.5 text-[11px] text-white/25 hover:text-white/40 transition-colors"
            >
              <Globe className="w-3 h-3" />
              <span>
                {webSources.length} web source{webSources.length !== 1 ? 's' : ''}
              </span>
              {showWebSources ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>

            {showWebSources && (
              <div className="space-y-1.5">
                {webSources.map((src, i) => (
                  <a
                    key={(src.url || '') + i}
                    href={src.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group flex items-start gap-2.5 px-3 py-2.5 rounded-lg bg-white/[0.02] border border-white/[0.05] hover:border-white/[0.08] transition-colors"
                  >
                    <span className="flex items-center justify-center size-5 rounded bg-white/[0.04] border border-white/[0.05] flex-shrink-0 mt-0.5">
                      <Favicon domain={src.domain} url={src.url} size={12} className="text-white/50" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[12px] font-semibold text-white/75 group-hover:text-white truncate">
                          {src.title || src.url}
                        </span>
                        <ExternalLink className="w-2.5 h-2.5 text-white/25 group-hover:text-emerald-400/70 flex-shrink-0" />
                      </div>
                      {src.snippet && (
                        <p className="text-[11px] text-white/30 leading-relaxed line-clamp-2 mt-0.5">
                          {src.snippet}
                        </p>
                      )}
                      <div className="text-[10px] text-emerald-400/50 mt-1 truncate">
                        {src.domain || src.url}
                      </div>
                    </div>
                  </a>
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
 * ThinkingGlow - displayed between the user message and the AI response while
 * Levy is working but before any tool card or token has arrived. Shows a
 * shimmering status label so the wait reads as active, not stuck. An optional
 * `label` lets callers describe the current activity (e.g. "Generating quiz").
 */
export function ThinkingGlow({ label = 'Thinking' }: { label?: string }) {
  return (
    <div className="flex justify-start px-4">
      <div className="flex items-center gap-2 py-3">
        <span className="relative flex size-2">
          <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400/60 animate-ping" />
          <span className="relative inline-flex size-2 rounded-full bg-emerald-400/80" />
        </span>
        <TextShimmer as="span" duration={1.6} className="text-[13px]">
          {`${label}…`}
        </TextShimmer>
      </div>
    </div>
  )
}
