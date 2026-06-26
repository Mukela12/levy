'use client'

/**
 * Turns a static answer page into a live conversation. The reader types a
 * follow-up (or just clicks Ask Levy) and lands in the full chat seeded with
 * the question, where they can keep asking. This is what makes the /answers
 * pages "not just static answers".
 */
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowUp } from 'lucide-react'

export function AnswerFollowup({ question }: { question: string }) {
  const [value, setValue] = useState('')
  const router = useRouter()

  function go(q: string) {
    const text = q.trim()
    if (!text) return
    router.push(`/chat?q=${encodeURIComponent(text)}`)
  }

  return (
    <div className="mt-8 rounded-2xl border border-emerald-500/20 bg-emerald-500/[0.04] p-4">
      <div className="text-[13.5px] font-medium text-white/85">Keep asking Levy</div>
      <p className="text-[12.5px] text-white/45 mt-0.5 mb-3">
        Ask a follow-up about your situation and continue the conversation with citations.
      </p>
      <div className="flex items-end gap-2">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              go(value)
            }
          }}
          rows={1}
          placeholder="e.g. What if my contract said something different?"
          className="flex-1 resize-none rounded-xl bg-background/60 border border-white/[0.10] px-3.5 py-2.5 text-[13.5px] text-white/85 placeholder:text-white/30 focus:outline-none focus:border-emerald-500/40"
        />
        <button
          type="button"
          onClick={() => go(value || question)}
          className="flex items-center justify-center size-10 shrink-0 rounded-xl bg-emerald-500/20 border border-emerald-500/30 text-emerald-100 hover:bg-emerald-500/30 transition-colors"
          aria-label="Ask Levy"
        >
          <ArrowUp size={16} />
        </button>
      </div>
      <button
        type="button"
        onClick={() => go(question)}
        className="mt-2.5 text-[12.5px] text-emerald-300/80 hover:text-emerald-200"
      >
        Or open this question in Levy →
      </button>
    </div>
  )
}
