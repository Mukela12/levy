'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
import { Download, RefreshCw, Loader2, Scale } from 'lucide-react'
import { generateBrief, type BriefResponse } from '@/lib/api'

interface BriefPanelProps {
  messages: Array<{ role: string; content: string }>
  token?: string
}

const typeLabels: Record<string, { letter: string; title: string }> = {
  issue: { letter: 'I', title: 'Issue' },
  rule: { letter: 'R', title: 'Rule' },
  application: { letter: 'A', title: 'Application' },
  conclusion: { letter: 'C', title: 'Conclusion' },
}

export function BriefPanel({ messages, token }: BriefPanelProps) {
  const [brief, setBrief] = useState<BriefResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const hasMessages = messages.length >= 2

  async function handleGenerate() {
    if (!hasMessages) return
    setLoading(true)
    setError(null)
    try {
      const result = await generateBrief(messages, token)
      setBrief(result)
    } catch (err) {
      setError('Failed to generate brief. Please try again.')
      console.error('Brief generation error:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full" style={{ overscrollBehavior: 'contain' }}>
      {/* Header */}
      <div className="px-5 py-4 border-b border-white/[0.06] flex items-center justify-between flex-shrink-0">
        <div>
          <h2
            className="text-xs font-bold tracking-[0.2em] uppercase text-emerald-400"
            style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
          >
            The Brief
          </h2>
          <span className="text-[10px] text-white/30">IRAC Analysis</span>
        </div>
        {brief && (
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="p-1.5 rounded-lg hover:bg-white/[0.04] text-white/30 hover:text-emerald-400 transition-colors"
            title="Refresh analysis"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-4" style={{ overscrollBehavior: 'contain' }}>
        {!brief && !loading && (
          <div className="flex flex-col items-center justify-center h-full text-center px-4">
            <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mb-4">
              <Scale size={20} className="text-emerald-400" />
            </div>
            <p className="text-[13px] text-white/50 mb-1">
              IRAC Legal Analysis
            </p>
            <p className="text-[11px] text-white/25 mb-6 leading-relaxed">
              {hasMessages
                ? 'Generate a structured Issue, Rule, Application, Conclusion analysis from this conversation.'
                : 'Start a conversation to generate a legal analysis.'}
            </p>
            <button
              onClick={handleGenerate}
              disabled={!hasMessages || loading}
              className={`px-4 py-2.5 rounded-xl text-xs font-semibold tracking-wide transition-all ${
                hasMessages
                  ? 'bg-emerald-600 text-white hover:bg-emerald-500 active:scale-[0.98]'
                  : 'bg-white/[0.04] text-white/20 cursor-not-allowed'
              }`}
            >
              Generate Analysis
            </button>
          </div>
        )}

        {loading && (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <Loader2 size={20} className="text-emerald-400 animate-spin" />
            <p className="text-[12px] text-white/40">Analyzing conversation...</p>
          </div>
        )}

        {error && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-4">
            <p className="text-[12px] text-red-400">{error}</p>
            <button
              onClick={handleGenerate}
              className="px-3 py-1.5 rounded-lg text-[11px] text-emerald-400 hover:bg-emerald-500/10 transition-colors"
            >
              Try again
            </button>
          </div>
        )}

        {brief && !loading && (
          <div className="space-y-5">
            {(['issue', 'rule', 'application', 'conclusion'] as const).map((type, i) => {
              const content = brief[type]
              if (!content) return null
              const { letter, title } = typeLabels[type]
              return (
                <motion.div
                  key={type}
                  initial={{ opacity: 0, x: 10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.1, duration: 0.4, ease: 'easeOut' }}
                  className="relative pl-4"
                >
                  <div className="absolute left-0 top-0 bottom-0 w-[3px] rounded-full bg-emerald-500/30" />
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-[10px] font-bold w-5 h-5 rounded flex items-center justify-center bg-emerald-500/10 text-emerald-400">
                      {letter}
                    </span>
                    <h3
                      className="text-sm font-semibold text-emerald-400"
                      style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
                    >
                      {title}
                    </h3>
                  </div>
                  <p className="text-[12px] leading-relaxed text-white/50">
                    {content}
                  </p>
                </motion.div>
              )
            })}

            {/* Citations */}
            {brief.citations && brief.citations.length > 0 && (
              <motion.div
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.4, duration: 0.4, ease: 'easeOut' }}
                className="pt-3 border-t border-white/[0.04]"
              >
                <h4 className="text-[10px] font-bold tracking-wider uppercase text-white/25 mb-2">
                  Sources Referenced
                </h4>
                <div className="space-y-1">
                  {brief.citations.map((c, i) => (
                    <div key={i} className="text-[11px] text-white/40 flex items-center gap-2">
                      <span className="w-1 h-1 rounded-full bg-emerald-400/50" />
                      <span>{c.act}, {c.section}</span>
                      {c.page > 0 && <span className="text-white/20">(p.{c.page})</span>}
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      {brief && (
        <div className="px-5 py-3 border-t border-white/[0.06] flex-shrink-0">
          <button
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-semibold tracking-wide bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/15 transition-colors"
          >
            <Download size={13} />
            Export Brief
          </button>
        </div>
      )}
    </div>
  )
}
