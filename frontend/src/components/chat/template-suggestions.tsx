'use client'

import { FileText, FileType2, Sparkles } from 'lucide-react'
import type { TemplateSuggestion } from '@/lib/api'

/**
 * Inline grid of template-suggestion cards rendered after the agent calls
 * `suggest_templates`. Up to 3 cards, responsive: 1col on mobile, 2col on
 * small tablets, 3col on desktop.
 */
export function TemplateSuggestions({
  templates,
  onUseTemplate,
}: {
  templates: TemplateSuggestion[]
  onUseTemplate: (template: TemplateSuggestion) => void
}) {
  if (!templates || templates.length === 0) return null

  return (
    <div className="my-3 -mx-1">
      <div className="flex items-center gap-1.5 mb-2 px-1">
        <Sparkles className="size-3 text-emerald-400/70" />
        <span className="text-[11px] uppercase tracking-wider text-white/40">
          Suggested templates
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
        {templates.slice(0, 3).map((t) => (
          <TemplateButton key={t.id} template={t} onClick={() => onUseTemplate(t)} />
        ))}
      </div>
    </div>
  )
}

function TemplateButton({
  template,
  onClick,
}: {
  template: TemplateSuggestion
  onClick: () => void
}) {
  const Icon = template.file_type === 'docx' ? FileType2 : FileText
  return (
    <button
      type="button"
      onClick={onClick}
      className="group text-left rounded-xl border border-white/[0.07] bg-white/[0.02] hover:border-emerald-500/30 hover:bg-emerald-500/[0.04] transition-colors p-3 flex flex-col gap-2 min-h-[112px]"
    >
      <div className="flex items-start gap-2.5">
        <span className={`flex items-center justify-center size-9 rounded-lg flex-shrink-0 ${typeBadge(template.file_type)}`}>
          <Icon size={15} className="opacity-90" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[12.5px] font-medium text-white/85 truncate group-hover:text-white">
            {template.name}
          </div>
          <div className="flex items-center gap-1.5 mt-0.5 text-[10px] text-white/35">
            <span className="uppercase tracking-wider">{template.file_type}</span>
            {template.page_count ? (
              <>
                <span className="text-white/15">·</span>
                <span>
                  {template.page_count} page{template.page_count === 1 ? '' : 's'}
                </span>
              </>
            ) : null}
          </div>
        </div>
      </div>
      {(template.description || template.preview) && (
        <p className="text-[11.5px] text-white/45 leading-snug line-clamp-3">
          {template.description || template.preview}
        </p>
      )}
      <div className="mt-auto pt-1 text-[10.5px] text-emerald-400/70 group-hover:text-emerald-400 transition-colors">
        Use this template →
      </div>
    </button>
  )
}

function typeBadge(type: TemplateSuggestion['file_type']): string {
  switch (type) {
    case 'docx':
      return 'bg-blue-500/10 border border-blue-500/20 text-blue-300'
    case 'pdf':
      return 'bg-red-500/10 border border-red-500/20 text-red-300'
    case 'md':
      return 'bg-purple-500/10 border border-purple-500/20 text-purple-300'
    case 'txt':
    default:
      return 'bg-white/[0.05] border border-white/[0.08] text-white/55'
  }
}
