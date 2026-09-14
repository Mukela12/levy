'use client'

/**
 * Canopy conversation view shared by the new-chat page (anonymous or
 * optimistic first turn) and the saved-chat page: heading, exchanges, the
 * floating composer with a jump-to-latest control, and the Brief aside on
 * wide screens. All real handlers are passed in; the drafting follow-ups are
 * composed here from onSend exactly as the legacy pages composed them.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ArrowDown, PanelRight } from 'lucide-react'
import { ChatMessage } from '@/components/chat/chat-message'
import type { Message } from '@/components/chat/chat-stream-context'
import { BriefPanel } from '@/components/chat/brief-panel'
import { useBrief } from '@/components/chat/brief-context'
import { usePdfViewer } from '@/components/chat/pdf-viewer-context'
import { CanopyComposer, type CanopyComposerProps } from './composer'

export interface CanopyConversationProps {
  title: string
  messages: Message[]
  loading: boolean
  onSend: (question: string) => void
  composer: Omit<CanopyComposerProps, 'onSend' | 'compact'>
  token?: string
  footNote?: ReactNode
}

export function CanopyConversation({ title, messages, loading, onSend, composer, token, footNote }: CanopyConversationProps) {
  const pdf = usePdfViewer()
  const brief = useBrief()
  const scrollRef = useRef<HTMLDivElement>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const [showLatest, setShowLatest] = useState(false)
  const nearBottomRef = useRef(true)

  // Follow the stream only while the reader is already near the bottom.
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const check = () => {
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight
      nearBottomRef.current = distance < 140
      setShowLatest(distance > 240)
    }
    check()
    el.addEventListener('scroll', check, { passive: true })
    return () => el.removeEventListener('scroll', check)
  }, [])
  useEffect(() => {
    if (nearBottomRef.current) endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  const drafts = {
    onUseTemplate: (t: { id: string; name: string }) =>
      onSend(`Use my "${t.name}" template (id: ${t.id}) to draft this for me. Generate the document with pdf_generate using that template's structure as the basis.`),
    onDraftBundle: (plan: { documents_to_file: string[]; procedural_mode: string; court_division: string }) =>
      onSend(`Proceed with the plan. Draft the full application bundle for me: ${plan.documents_to_file.join(', ')}. Apply the heading and party block consistent with a Zambian ${plan.procedural_mode} in the ${plan.court_division}. Cause number is "[CAUSE NUMBER TO BE ALLOCATED]" unless I gave you one earlier.`),
    onDraftIndividual: (plan: { procedural_mode: string; court_division: string }, kind: 'summons' | 'affidavit' | 'skeletal' | 'order') => {
      const map: Record<string, string> = {
        summons: 'the Originating Notice of Motion / Summons',
        affidavit: 'the Affidavit in Support',
        skeletal: 'the Skeletal Arguments',
        order: 'the Draft Order',
      }
      onSend(`Proceed with the plan. Draft ${map[kind]} only, using the Zambian ${plan.procedural_mode} format for the ${plan.court_division}. Cause number is "[CAUSE NUMBER TO BE ALLOCATED]" unless I gave you one earlier.`)
    },
  }

  return (
    <div className="cp-harness">
      <div className="cp-harness-chat">
        <div ref={scrollRef} className="cp-harness-scroll">
          <div className="cp-harness-inner">
            <div className="cp-harness-heading">
              <span>{title}</span>
              {brief.available && (
                <button type="button" className="cp-icon-btn" aria-label="Open IRAC analysis" onClick={() => brief.setOpen(true)}>
                  <PanelRight size={18} />
                </button>
              )}
            </div>
            {messages.map((msg, i) => {
              const isLastAssistant = loading && i === messages.length - 1 && msg.role === 'assistant'
              return (
                <div key={msg.id ?? i} className="cp-exchange">
                  <ChatMessage
                    messageId={msg.id}
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
                    onOpenCitation={(c) => pdf.open({ documentId: c.document_id, actName: c.act_name, pageStart: c.page_start, pageEnd: c.page_end, section: c.section })}
                    onOpenArtifact={(a) => pdf.open({ artifactId: a.id, actName: a.title, pageStart: 1 })}
                    onUseTemplate={drafts.onUseTemplate}
                    onDraftBundle={drafts.onDraftBundle}
                    onDraftIndividual={drafts.onDraftIndividual}
                  />
                </div>
              )
            })}
            <div ref={endRef} />
          </div>
        </div>
        <div className="cp-harness-composer">
          <div style={{ position: 'relative' }}>
            {showLatest && (
              <button type="button" className="cp-jump-latest" onClick={() => endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })}>
                <ArrowDown size={15} /> Latest response
              </button>
            )}
            <CanopyComposer {...composer} onSend={onSend} compact />
            <p className="cp-harness-foot">{footNote ?? 'Levy provides legal information, not legal advice.'}</p>
          </div>
        </div>
      </div>
      {messages.length > 0 && (
        <aside className="cp-brief-aside">
          <BriefPanel messages={messages.map((m) => ({ role: m.role, content: m.content }))} token={token} />
        </aside>
      )}
    </div>
  )
}
