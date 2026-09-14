'use client'

/**
 * Canopy rendering of one message. Same props and callbacks as the legacy
 * ChatMessage; the difference is presentation: a question group on the
 * right, an answer surface with the tool activity summarised in one line,
 * the same specialised cards (plans, entitlements, precedent, study), and
 * the sources panel with conservative citation badges.
 */

import { useState, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { AlertCircle, Check, CheckCircle2, ChevronDown, Clock, Copy, Loader2, Paperclip, Scale } from 'lucide-react'
import { ActionArt } from './action-art'
import { TextShimmer } from '@/components/ui/text-shimmer'
import { AgentTask, TOOL_META } from '@/components/chat/agent-task'
import type { ToolCallView } from '@/components/chat/tool-call-card'
import { ArtifactCard } from '@/components/chat/artifact-card'
import { TemplateSuggestions } from '@/components/chat/template-suggestions'
import { ApplicationPlanCard } from '@/components/chat/application-plan-card'
import { EntitlementCard } from '@/components/chat/entitlement-card'
import { PrecedentCard } from '@/components/chat/precedent-card'
import { CheatSheetCard } from '@/components/chat/cheat-sheet-card'
import { QuizCard } from '@/components/chat/quiz-card'
import { AnswerFeedback } from '@/components/chat/answer-feedback'
import { useBrief } from '@/components/chat/brief-context'
import type { ChatMessageProps, MessageBlock } from '@/components/chat/chat-message'
import type { ChunkUsed } from '@/lib/api'
import { AnswerSources } from './answer-sources'

function kindLabel(toolCalls: ToolCallView[] | undefined): string {
  const names = new Set((toolCalls || []).map((c) => c.name))
  if ([...names].some((n) => n.startsWith('draft_') || n === 'pdf_generate' || n === 'fill_form')) return 'Working draft'
  if (names.has('calculate_entitlements')) return 'Calculation'
  if (names.has('generate_quiz') || names.has('make_cheat_sheet')) return 'Study'
  if (names.has('search_case_law')) return 'Research with authorities'
  if (names.size) return 'Research'
  return 'Answer'
}

function describeInput(call: ToolCallView): string {
  const i = call.input || {}
  const v = (i.query ?? i.url ?? i.title ?? i.document_id ?? i.topic ?? '') as string
  return typeof v === 'string' ? v.slice(0, 120) : ''
}

/** One line for what the tools did, expandable to the real per-tool cards. */
export function Activity({ toolCalls, isStreaming }: { toolCalls: ToolCallView[]; isStreaming?: boolean }) {
  const [open, setOpen] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  if (!toolCalls.length) return null
  const running = toolCalls.find((c) => c.status === 'running')
  const failed = toolCalls.filter((c) => c.status === 'error').length
  const done = toolCalls.filter((c) => c.status === 'ok').length
  const total = toolCalls.length
  const label = running
    ? (TOOL_META[running.name]?.verb ?? `Running ${running.name}`) + '…'
    : failed
      ? `${done} of ${total} ${total === 1 ? 'step' : 'steps'} complete · ${failed} unavailable`
      : `${total} ${total === 1 ? 'step' : 'steps'} completed`
  const state = running || (isStreaming && !toolCalls.some((c) => c.status !== 'running')) ? 'is-working' : failed ? 'is-failed' : 'is-complete'
  return (
    <div className={'cp-activity ' + state}>
      <button type="button" className="cp-activity-summary" aria-expanded={open} aria-label={'Tool activity: ' + label} onClick={() => setOpen((v) => !v)}>
        {running ? <Loader2 size={14} className="animate-spin" /> : failed ? <AlertCircle size={14} /> : <Check size={14} />}
        <span role="status">{label}</span>
        <ChevronDown size={13} className={open ? 'is-open' : ''} />
      </button>
      {open && (
        <ol className="cp-activity-list">
          {toolCalls.map((c) => {
            const meta = TOOL_META[c.name]
            const isOpen = expanded.has(c.id)
            const results = (c.db?.length || 0) + (c.web?.length || 0)
            return (
              <li key={c.id}>
                <button
                  type="button"
                  className="cp-activity-step"
                  style={{ width: '100%', textAlign: 'left' }}
                  aria-expanded={isOpen}
                  onClick={() =>
                    setExpanded((prev) => {
                      const n = new Set(prev)
                      if (n.has(c.id)) n.delete(c.id)
                      else n.add(c.id)
                      return n
                    })
                  }
                >
                  {c.status === 'running' ? <Loader2 size={14} className="animate-spin" /> : c.status === 'ok' ? <CheckCircle2 size={14} className="tool-done" /> : c.status === 'error' ? <AlertCircle size={14} className="tool-error" /> : <span className="cp-tool-circle" />}
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <strong>{meta?.label ?? c.name}</strong>
                    <small>{describeInput(c) || meta?.verb || ''}{results ? ` · ${results} ${results === 1 ? 'result' : 'results'}` : ''}</small>
                  </div>
                  <span className="cp-tool-state">{c.status === 'ok' ? 'Done' : c.status === 'running' ? 'Working' : 'Unavailable'}</span>
                </button>
                {isOpen && (
                  <div className="cp-activity-detail">
                    <AgentTask call={c} />
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}

export function CanopyMessage(props: ChatMessageProps) {
  const {
    messageId, role, content, blocks, citations, webSources, toolCalls, artifacts,
    templateSuggestions, applicationPlans, entitlementBreakdowns, caseLaw, cheatSheets, quizzes,
    timing, isStreaming, compaction, onOpenCitation, onOpenArtifact, onUseTemplate, onDraftBundle, onDraftIndividual,
  } = props
  const brief = useBrief()
  const [copied, setCopied] = useState(false)

  if (role === 'user') {
    const attachBlock = blocks?.find((b): b is Extract<MessageBlock, { kind: 'attachments' }> => b.kind === 'attachments')
    const docs = attachBlock?.docs ?? []
    return (
      <div className="cp-question-group">
        <div className="cp-question-byline"><span>You</span></div>
        {docs.length > 0 && (
          <div className="cp-question-chips">
            {docs.map((d) => (
              <span key={d.id} className="cp-chip"><Paperclip size={11} /><span className="cp-chip-title">{d.title}</span></span>
            ))}
          </div>
        )}
        <div className="cp-question"><p>{content}</p></div>
      </div>
    )
  }

  const open = (documentId: string, title: string) =>
    onOpenCitation?.({ document_id: documentId, act_name: title, page_start: 1 } as ChunkUsed)

  const rendered: ReactNode[] = []
  if (blocks && blocks.length > 0) {
    blocks.forEach((block, idx) => {
      if (block.kind === 'text') {
        if (!block.text) return
        const last = idx === blocks.length - 1
        rendered.push(
          <div key={`t-${idx}`}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.text}</ReactMarkdown>
            {isStreaming && last && <span className="cp-cursor" aria-hidden="true" />}
          </div>,
        )
        return
      }
      if (block.kind === 'templates') {
        const suggestions = block.templates ?? templateSuggestions?.[block.toolCallId] ?? []
        if (suggestions.length) rendered.push(<TemplateSuggestions key={`ts-${block.toolCallId}`} templates={suggestions} onUseTemplate={(t) => onUseTemplate?.(t)} />)
        return
      }
      if (block.kind === 'application_plan') {
        const plan = block.plan ?? applicationPlans?.[block.toolCallId]
        if (plan) rendered.push(<ApplicationPlanCard key={`ap-${block.toolCallId}`} plan={plan} onDraftBundle={onDraftBundle ? () => onDraftBundle(plan) : undefined} onDraftIndividual={onDraftIndividual ? (kind) => onDraftIndividual(plan, kind) : undefined} />)
        return
      }
      if (block.kind === 'entitlement') {
        const breakdown = block.breakdown ?? entitlementBreakdowns?.[block.toolCallId]
        if (breakdown) rendered.push(<EntitlementCard key={`ent-${block.toolCallId}`} breakdown={breakdown} />)
        return
      }
      if (block.kind === 'case_law') {
        const cases = block.cases ?? caseLaw?.[block.toolCallId]
        if (cases?.length) rendered.push(<PrecedentCard key={`law-${block.toolCallId}`} cases={cases} onOpenCase={open} />)
        return
      }
      if (block.kind === 'cheat_sheet') {
        const sheet = block.cheatSheet ?? cheatSheets?.[block.toolCallId]
        if (sheet) rendered.push(<CheatSheetCard key={`cs-${block.toolCallId}`} sheet={sheet} />)
        return
      }
      if (block.kind === 'quiz') {
        const quiz = block.quiz ?? quizzes?.[block.toolCallId]
        if (quiz?.questions?.length) rendered.push(<QuizCard key={`quiz-${block.toolCallId}`} quiz={quiz} />)
        return
      }
      // tool / attachments / citation_audit blocks: the activity line and the
      // sources panel present these; nothing is dropped.
    })
  } else if (content) {
    rendered.push(
      <div key="legacy">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        {isStreaming && <span className="cp-cursor" aria-hidden="true" />}
      </div>,
    )
  }

  const nothingYet = isStreaming && !content && (!blocks || blocks.length === 0) && !(toolCalls && toolCalls.length)
  const lastBlock = blocks?.[blocks.length - 1]
  const toolRunning = (toolCalls || []).some((c) => c.status === 'running')
  const composingGap = isStreaming && blocks && blocks.length > 0 && !toolRunning && lastBlock && lastBlock.kind !== 'text'

  async function copyAnswer() {
    try {
      const text = (blocks || []).filter((b): b is Extract<MessageBlock, { kind: 'text' }> => b.kind === 'text').map((b) => b.text).join('\n\n') || content
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <div className="cp-answer">
      {compaction && (
        <div className="cp-compaction">
          <Scale size={13} />
          <span>Earlier conversation summarised to keep the thread within context ({compaction.summarised_messages} messages compressed). The full transcript is in the Brief.</span>
        </div>
      )}
      <div className="cp-answer-byline">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/levy-logo.svg" alt="" width={26} height={26} draggable={false} />
        <strong>Levy</strong>
        <span className="cp-kind">{kindLabel(toolCalls)}</span>
      </div>
      <div className="cp-answer-surface">
        {toolCalls && toolCalls.length > 0 && <Activity toolCalls={toolCalls} isStreaming={isStreaming} />}
        <div className="cp-answer-body">{rendered}</div>
        {nothingYet && (
          <div className="cp-working"><span className="cp-ping" aria-hidden="true" /><TextShimmer as="span" duration={1.6}>Thinking…</TextShimmer></div>
        )}
        {composingGap && (
          <div className="cp-working"><span className="cp-ping" aria-hidden="true" /><TextShimmer as="span" duration={1.6}>Working…</TextShimmer></div>
        )}
        {artifacts && artifacts.length > 0 && (
          <div className="cp-artifacts">
            {artifacts.map((art) => <ArtifactCard key={art.id} artifact={art} onOpen={() => onOpenArtifact?.(art)} />)}
          </div>
        )}
        {!isStreaming && (
          <AnswerSources citations={citations} webSources={webSources} blocks={blocks} onOpenPassage={(p) => onOpenCitation?.(p)} onOpenDocument={open} />
        )}
        {!isStreaming && (content || rendered.length > 0) && (
          <div className="cp-result-actions">
            {brief.available && (
              <button type="button" onClick={() => brief.setOpen(true)} className="cp-brief-action"><ActionArt kind="irac" size={24} /> IRAC analysis</button>
            )}
            <button type="button" onClick={copyAnswer} aria-label={copied ? 'Answer copied' : 'Copy answer'}>{copied ? <Check size={15} /> : <Copy size={15} />} {copied ? 'Copied' : 'Copy answer'}</button>
            {timing && <span className="cp-timing"><Clock size={12} />{(timing.total_ms / 1000).toFixed(1)}s</span>}
            <span className="cp-rating">{messageId && <AnswerFeedback messageId={messageId} />}</span>
          </div>
        )}
      </div>
    </div>
  )
}
