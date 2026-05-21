'use client'

/**
 * Renders one tool invocation as a nested "task" with its results listed as
 * subtasks below - visual style adapted from the AgentPlan reference component.
 *
 * Each subtask has an appropriate icon: FileText for corpus/document hits,
 * favicons for web hits (with a generic Globe fallback).
 */

import { useState } from 'react'
import { motion, AnimatePresence, LayoutGroup } from 'framer-motion'
import {
  CheckCircle2,
  CircleDotDashed,
  CircleX,
  ChevronRight,
  Database,
  Globe as GlobeIcon,
  Search,
  Link as LinkIcon,
  ExternalLink,
  FileText,
  FilePen,
  Scale,
  Gavel,
  Files as FilesIcon,
  Sparkles,
  ClipboardList,
} from 'lucide-react'
import { Favicon } from './favicon'
import type { ToolCallView } from './tool-call-card'

const TOOL_META: Record<
  string,
  { label: string; verb: string; Icon: typeof Search }
> = {
  search_corpus: { label: 'Corpus search', verb: 'Searching the corpus', Icon: Database },
  gov_search: { label: 'Gov search', verb: 'Searching government sources', Icon: Search },
  web_search: { label: 'Web search', verb: 'Searching the web', Icon: GlobeIcon },
  web_fetch: { label: 'Read page', verb: 'Reading page', Icon: LinkIcon },
  web_crawl: { label: 'Crawl site', verb: 'Crawling site', Icon: LinkIcon },
  // PDF tooling — give each one a verb that tells the user what Levy is
  // doing right now ("Drafting the Affidavit in Support…") rather than a
  // generic "Running tool" string. Same pattern as the corpus-search row.
  pdf_extract_pages: { label: 'Extract pages', verb: 'Extracting pages from the corpus', Icon: FileText },
  pdf_generate: { label: 'Generate PDF', verb: 'Drafting your document as a PDF', Icon: FilePen },
  pdf_split: { label: 'Split PDF', verb: 'Splitting the PDF into parts', Icon: FileText },
  pdf_merge: { label: 'Merge PDFs', verb: 'Merging PDFs', Icon: FilesIcon },
  export_thread_brief: { label: 'Export brief', verb: 'Exporting the thread as a brief', Icon: FileText },
  suggest_templates: { label: 'Templates', verb: 'Finding matching templates', Icon: Sparkles },
  // Application-drafting tools — these are the slowest and benefit most
  // from a clear "working on…" indicator.
  recommend_application: { label: 'Plan', verb: 'Planning the application', Icon: ClipboardList },
  draft_legal_document: { label: 'Draft', verb: 'Drafting the document', Icon: FilePen },
  fill_form: { label: 'Fill form', verb: 'Completing the form', Icon: ClipboardList },
  draft_summons: { label: 'Summons', verb: 'Drafting the Originating Notice of Motion', Icon: FilePen },
  draft_affidavit: { label: 'Affidavit', verb: 'Drafting the Affidavit in Support', Icon: FilePen },
  draft_skeletal: { label: 'Skeletal', verb: 'Drafting Skeletal Arguments', Icon: Scale },
  draft_order: { label: 'Draft Order', verb: 'Drafting the Draft Order', Icon: Gavel },
  draft_application_bundle: { label: 'Bundle', verb: 'Assembling the application bundle', Icon: FilesIcon },
}

function describeArg(name: string, input: Record<string, unknown>): string {
  if (typeof input?.query === 'string') return input.query as string
  if (typeof input?.url === 'string') return input.url as string
  if (typeof input?.start_url === 'string') return input.start_url as string
  if (typeof input?.title === 'string') return input.title as string
  // Drafting tools: surface "X v Y" so the user can see which matter the
  // tool is working on at a glance, rather than a wall of key=value pairs.
  if (
    name === 'draft_summons' ||
    name === 'draft_affidavit' ||
    name === 'draft_skeletal' ||
    name === 'draft_order' ||
    name === 'draft_application_bundle' ||
    name === 'recommend_application'
  ) {
    const a = (input?.applicant_name || input?.cause_of_action || '') as string
    const r = (input?.respondent_name || '') as string
    if (a && r) return `${a} v ${r}`
    if (a) return a
    return ''
  }
  return Object.entries(input || {})
    .filter(([k]) => k !== 'top_k' && k !== 'threshold' && k !== 'max_results')
    .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
    .join(', ')
}

export function AgentTask({ call }: { call: ToolCallView }) {
  const [expanded, setExpanded] = useState(false)
  const meta = TOOL_META[call.name] ?? {
    label: call.name,
    verb: `Running ${call.name}`,
    Icon: Search,
  }
  const Icon = meta.Icon

  const arg = describeArg(call.name, call.input)
  const dbResults = call.db ?? []
  const webResults = call.web ?? []
  const total = dbResults.length + webResults.length
  const hasResults = call.status === 'ok' && total > 0
  const isRunning = call.status === 'running'

  // Top-line status icon
  const StatusIcon =
    call.status === 'ok' ? CheckCircle2 :
    call.status === 'error' ? CircleX :
    CircleDotDashed
  const statusTint =
    call.status === 'ok' ? 'text-emerald-400' :
    call.status === 'error' ? 'text-red-400' :
    'text-blue-400'

  return (
    <LayoutGroup>
      <motion.div
        layout
        className="rounded-lg border border-white/[0.06] bg-white/[0.015] overflow-hidden"
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: [0.2, 0.65, 0.3, 0.9] }}
      >
        {/* Task row */}
        <button
          type="button"
          onClick={() => hasResults && setExpanded((v) => !v)}
          className={`w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors ${
            hasResults ? 'hover:bg-white/[0.025] cursor-pointer' : 'cursor-default'
          }`}
        >
          {/* Status icon - animates between run/done states */}
          <span className="flex-shrink-0">
            <AnimatePresence mode="wait">
              <motion.div
                key={call.status}
                initial={{ opacity: 0, scale: 0.8, rotate: -10 }}
                animate={{ opacity: 1, scale: 1, rotate: 0 }}
                exit={{ opacity: 0, scale: 0.8, rotate: 10 }}
                transition={{ duration: 0.2, ease: [0.2, 0.65, 0.3, 0.9] }}
              >
                <StatusIcon
                  className={`size-4 ${statusTint} ${isRunning ? 'animate-spin' : ''}`}
                />
              </motion.div>
            </AnimatePresence>
          </span>

          {/* Tool icon + verb + arg */}
          <span className="flex items-center justify-center size-6 rounded-md bg-emerald-500/[0.06] text-emerald-400/80 flex-shrink-0">
            <Icon className="size-3.5" />
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 text-[12px] text-white/75">
              <span className="font-medium truncate">
                {isRunning ? meta.verb : meta.label}
              </span>
              {arg && (
                <span className="text-white/35 truncate">
                  {arg.length > 60 ? arg.slice(0, 57) + '…' : arg}
                </span>
              )}
            </div>
            {!isRunning && (
              <div className="flex items-center gap-2 text-[10.5px] text-white/30 mt-0.5">
                {dbResults.length > 0 && (
                  <span>
                    {dbResults.length} corpus match
                    {dbResults.length === 1 ? '' : 'es'}
                  </span>
                )}
                {dbResults.length > 0 && webResults.length > 0 && (
                  <span className="text-white/15">·</span>
                )}
                {webResults.length > 0 && (
                  <span>
                    {webResults.length} web result
                    {webResults.length === 1 ? '' : 's'}
                  </span>
                )}
                {dbResults.length === 0 && webResults.length === 0 && (
                  <span>{call.status === 'error' ? (call.resultPreview ?? 'tool failed') : 'no matches'}</span>
                )}
                {typeof call.durationMs === 'number' && total > 0 && (
                  <>
                    <span className="text-white/15">·</span>
                    <span>{(call.durationMs / 1000).toFixed(1)}s</span>
                  </>
                )}
              </div>
            )}
          </div>

          {hasResults && (
            <motion.span
              animate={{ rotate: expanded ? 90 : 0 }}
              transition={{ duration: 0.2 }}
              className="flex items-center justify-center size-5 text-white/30 flex-shrink-0"
            >
              <ChevronRight className="size-3.5" />
            </motion.span>
          )}
        </button>

        {/* Subtasks - staggered reveal, with vertical dashed connector */}
        <AnimatePresence initial={false}>
          {expanded && hasResults && (
            <motion.div
              key="subtasks"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25, ease: [0.2, 0.65, 0.3, 0.9] }}
              className="relative overflow-hidden border-t border-white/[0.04]"
            >
              {/* Vertical dashed connector aligned with the tool icon */}
              <div className="absolute top-1.5 bottom-1.5 left-[26px] border-l border-dashed border-white/15" />

              <ul className="py-1.5 pl-3 pr-2.5 space-y-0.5">
                {dbResults.map((s, i) => (
                  <SubtaskRow
                    key={(s.id ?? '') + 'db' + i}
                    icon={
                      <span className="flex items-center justify-center size-5 rounded-md bg-red-500/[0.08] border border-red-500/[0.15]">
                        <FileText className="size-3 text-red-400/80" />
                      </span>
                    }
                    title={s.act_name}
                    detail={[
                      s.section ? `S.${s.section}` : null,
                      s.page_start ? `p.${s.page_start}` : null,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                    delay={i * 0.04}
                  />
                ))}
                {webResults.map((s, i) => (
                  <SubtaskRow
                    key={(s.url ?? '') + 'w' + i}
                    icon={
                      <span className="flex items-center justify-center size-5 rounded-md bg-white/[0.04] border border-white/[0.06]">
                        <Favicon domain={s.domain} url={s.url} size={11} className="text-white/55" />
                      </span>
                    }
                    title={s.title || s.url}
                    detail={s.domain || s.url}
                    href={s.url}
                    delay={(dbResults.length + i) * 0.04}
                  />
                ))}
              </ul>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </LayoutGroup>
  )
}

function SubtaskRow({
  icon,
  title,
  detail,
  href,
  delay,
}: {
  icon: React.ReactNode
  title?: string
  detail?: string
  href?: string
  delay?: number
}) {
  const Body = (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.22, ease: [0.2, 0.65, 0.3, 0.9], delay }}
      className="group flex items-center gap-2.5 pl-7 pr-2 py-1 rounded-md hover:bg-white/[0.025]"
    >
      <span className="-ml-[28px] z-[1]">{icon}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-[11.5px] text-white/75 truncate">{title}</span>
          {href && (
            <ExternalLink className="size-2.5 text-white/25 group-hover:text-emerald-400/70 flex-shrink-0" />
          )}
        </div>
        {detail && <div className="text-[10px] text-white/30 truncate">{detail}</div>}
      </div>
    </motion.div>
  )

  if (href) {
    return (
      <li>
        <a href={href} target="_blank" rel="noopener noreferrer" className="block">
          {Body}
        </a>
      </li>
    )
  }
  return <li>{Body}</li>
}
