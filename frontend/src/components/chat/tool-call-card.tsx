'use client'

import { useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Search,
  Globe,
  Database,
  ExternalLink,
  Link as LinkIcon,
  GraduationCap,
  ScrollText,
  FileText,
  PenLine,
  Calculator,
  Scale,
  Newspaper,
} from 'lucide-react'
import { Favicon } from './favicon'
import { TextShimmer } from '@/components/ui/text-shimmer'

export interface ToolCallView {
  id: string
  name: string
  input: Record<string, unknown>
  status: 'running' | 'ok' | 'error'
  resultPreview?: string | null
  durationMs?: number
  db?: Array<{
    id?: string
    act_name?: string
    section?: string
    page_start?: number
  }>
  web?: Array<{
    title?: string
    url?: string
    domain?: string
  }>
}

const TOOL_LABELS: Record<string, { label: string; verb: string; Icon: typeof Search }> = {
  search_corpus: { label: 'Corpus', verb: 'Searching the corpus', Icon: Database },
  gov_search: { label: 'Gov sites', verb: 'Searching government sources', Icon: Search },
  web_search: { label: 'Web', verb: 'Searching the web', Icon: Globe },
  web_crawl: { label: 'Web', verb: 'Crawling the site', Icon: Globe },
  news_search: { label: 'News', verb: 'Searching the news', Icon: Newspaper },
  web_fetch: { label: 'Fetch', verb: 'Reading the page', Icon: LinkIcon },
  fetch_web_pdf: { label: 'Fetch', verb: 'Fetching the document', Icon: LinkIcon },
  search_case_law: { label: 'Case law', verb: 'Searching case law', Icon: Scale },
  calculate_entitlements: { label: 'Entitlements', verb: 'Calculating entitlements', Icon: Calculator },
  recommend_application: { label: 'Plan', verb: 'Planning the application', Icon: Scale },
  make_cheat_sheet: { label: 'Cheat sheet', verb: 'Generating your cheat sheet', Icon: ScrollText },
  generate_quiz: { label: 'Quiz', verb: 'Generating your quiz', Icon: GraduationCap },
  pdf_generate: { label: 'Document', verb: 'Generating the document', Icon: FileText },
  draft_legal_document: { label: 'Draft', verb: 'Drafting the document', Icon: PenLine },
  draft_summons: { label: 'Draft', verb: 'Drafting the summons', Icon: PenLine },
  draft_affidavit: { label: 'Draft', verb: 'Drafting the affidavit', Icon: PenLine },
  draft_skeletal: { label: 'Draft', verb: 'Drafting the skeleton arguments', Icon: PenLine },
  draft_order: { label: 'Draft', verb: 'Drafting the order', Icon: PenLine },
  draft_application_bundle: { label: 'Bundle', verb: 'Assembling the bundle', Icon: FileText },
  fill_form: { label: 'Form', verb: 'Filling the form', Icon: FileText },
  suggest_templates: { label: 'Templates', verb: 'Finding templates', Icon: FileText },
  export_thread_brief: { label: 'Brief', verb: 'Building the brief', Icon: FileText },
  pdf_extract_pages: { label: 'Extract', verb: 'Extracting pages', Icon: FileText },
  pdf_merge: { label: 'Merge', verb: 'Merging documents', Icon: FileText },
  pdf_split: { label: 'Split', verb: 'Splitting the document', Icon: FileText },
}

function formatInput(name: string, input: Record<string, unknown>): string {
  if (typeof input?.query === 'string') return input.query as string
  if (typeof input?.url === 'string') return input.url as string
  return Object.entries(input || {})
    .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
    .join(', ')
}

export function ToolCallCard({ call }: { call: ToolCallView }) {
  const [expanded, setExpanded] = useState(false)
  const meta = TOOL_LABELS[call.name] ?? {
    label: call.name,
    verb: `Running ${call.name}`,
    Icon: Search,
  }
  const Icon = meta.Icon

  const arg = formatInput(call.name, call.input)
  const dbCount = call.db?.length ?? 0
  const webCount = call.web?.length ?? 0
  const hasResults = call.status === 'ok' && (dbCount > 0 || webCount > 0)

  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.015] overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-white/[0.02]"
      >
        <span className="flex items-center justify-center size-6 rounded-md bg-emerald-500/10 text-emerald-400 flex-shrink-0">
          {call.status === 'running' ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : call.status === 'ok' ? (
            <Icon className="size-3.5" />
          ) : (
            <AlertTriangle className="size-3.5 text-amber-400" />
          )}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-[12px] text-white/70">
            {call.status === 'running' ? (
              <TextShimmer as="span" duration={1.6} className="font-medium text-[12px]">
                {meta.verb}
              </TextShimmer>
            ) : (
              <span className="font-medium">{meta.label}</span>
            )}
            {arg && (
              <span className="text-white/35 truncate">
                {arg.length > 64 ? arg.slice(0, 61) + '…' : arg}
              </span>
            )}
          </div>
          {call.status === 'ok' && (
            <div className="flex items-center gap-2 text-[10.5px] text-white/30 mt-0.5">
              {dbCount > 0 && <span>{dbCount} corpus match{dbCount === 1 ? '' : 'es'}</span>}
              {dbCount > 0 && webCount > 0 && <span className="text-white/15">·</span>}
              {webCount > 0 && <span>{webCount} web result{webCount === 1 ? '' : 's'}</span>}
              {dbCount === 0 && webCount === 0 && <span>no matches</span>}
              {typeof call.durationMs === 'number' && (
                <>
                  <span className="text-white/15">·</span>
                  <span>{(call.durationMs / 1000).toFixed(1)}s</span>
                </>
              )}
            </div>
          )}
          {call.status === 'error' && (
            <div className="text-[10.5px] text-amber-400/70 mt-0.5">
              {call.resultPreview || 'tool failed'}
            </div>
          )}
        </div>
        {hasResults && (
          <span className="flex items-center justify-center size-5 text-white/30 flex-shrink-0">
            {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
          </span>
        )}
      </button>

      {expanded && hasResults && (
        <div className="border-t border-white/[0.05] px-3 py-2.5 space-y-2 bg-black/20">
          {dbCount > 0 && (
            <div className="space-y-1">
              {call.db!.map((s, i) => (
                <div key={s.id || i} className="flex items-center gap-2 text-[11px]">
                  <CheckCircle2 className="size-3 text-emerald-400/60 flex-shrink-0" />
                  <span className="text-emerald-400/80 font-medium">{s.act_name}</span>
                  {s.section && <span className="text-white/30">S.{s.section}</span>}
                  {s.page_start && <span className="text-white/25">p.{s.page_start}</span>}
                </div>
              ))}
            </div>
          )}
          {webCount > 0 && (
            <div className="space-y-1">
              {call.web!.map((s, i) => (
                <a
                  key={(s.url || '') + i}
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group flex items-start gap-2 text-[11px] hover:bg-white/[0.02] -mx-1 px-1 py-1 rounded"
                >
                  <Favicon domain={s.domain} url={s.url} size={12} className="text-white/30 flex-shrink-0 mt-0.5" />
                  <div className="min-w-0 flex-1">
                    <div className="text-white/70 truncate flex items-center gap-1">
                      <span className="truncate">{s.title || s.url}</span>
                      <ExternalLink className="size-2.5 text-white/25 group-hover:text-emerald-400/70 flex-shrink-0" />
                    </div>
                    <div className="text-white/30 text-[10px] truncate">{s.domain || s.url}</div>
                  </div>
                </a>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
