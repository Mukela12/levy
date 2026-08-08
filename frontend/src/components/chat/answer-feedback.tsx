'use client'

import { useState } from 'react'
import { ThumbsUp, ThumbsDown } from 'lucide-react'
import { submitFeedback, clearFeedback } from '@/lib/api'

/**
 * Thumbs up/down on one of Levy's answers.
 *
 * Until this shipped, nothing in Levy recorded whether an answer was any
 * good — every quality judgement came from reading conversations by hand,
 * which does not scale and misses everyone who silently gave up. A
 * thumbs-down opens a one-line "what was wrong?" box, because the reason is
 * worth far more than the count.
 *
 * Deliberately quiet: it sits at the same weight as the timing readout and
 * only gains colour once used, so it never competes with the answer itself.
 */
export function AnswerFeedback({ messageId }: { messageId: string }) {
  const [rating, setRating] = useState<'up' | 'down' | null>(null)
  const [askReason, setAskReason] = useState(false)
  const [reason, setReason] = useState('')
  const [sent, setSent] = useState(false)
  const [failed, setFailed] = useState(false)

  async function vote(next: 'up' | 'down') {
    setFailed(false)
    // Clicking the same thumb again clears the vote.
    if (rating === next) {
      setRating(null)
      setAskReason(false)
      try {
        await clearFeedback(messageId)
      } catch {
        setFailed(true)
      }
      return
    }
    setRating(next)
    setAskReason(next === 'down')
    try {
      await submitFeedback(messageId, next)
    } catch {
      setFailed(true)
    }
  }

  async function sendReason() {
    const text = reason.trim()
    if (!text) {
      setAskReason(false)
      return
    }
    setAskReason(false)
    setSent(true)
    try {
      await submitFeedback(messageId, 'down', text)
    } catch {
      setFailed(true)
    }
  }

  const base =
    'p-1 rounded transition-colors duration-150 hover:bg-white/[0.06] disabled:opacity-40'

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-0.5">
        <button
          type="button"
          onClick={() => vote('up')}
          aria-label="This answer was helpful"
          aria-pressed={rating === 'up'}
          className={base}
        >
          <ThumbsUp
            className={`w-3 h-3 ${
              rating === 'up' ? 'text-emerald-400' : 'text-white/15 hover:text-white/40'
            }`}
          />
        </button>
        <button
          type="button"
          onClick={() => vote('down')}
          aria-label="This answer was not helpful"
          aria-pressed={rating === 'down'}
          className={base}
        >
          <ThumbsDown
            className={`w-3 h-3 ${
              rating === 'down' ? 'text-amber-400' : 'text-white/15 hover:text-white/40'
            }`}
          />
        </button>
        {sent && <span className="text-[10px] text-white/25 ml-1">Thanks — noted.</span>}
        {failed && (
          <span className="text-[10px] text-white/25 ml-1">
            Could not save that. Your answer is unaffected.
          </span>
        )}
      </div>

      {askReason && (
        <div className="flex items-center gap-1.5">
          <input
            autoFocus
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') sendReason()
              if (e.key === 'Escape') setAskReason(false)
            }}
            placeholder="What was wrong? (optional)"
            maxLength={2000}
            className="flex-1 max-w-sm bg-white/[0.03] border border-white/10 rounded px-2 py-1 text-[11px] text-white/80 placeholder-white/25 focus:outline-none focus:border-white/25"
          />
          <button
            type="button"
            onClick={sendReason}
            className="text-[10.5px] text-white/45 hover:text-white/80 px-1.5 py-1"
          >
            Send
          </button>
        </div>
      )}
    </div>
  )
}
