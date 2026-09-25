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
 * It used to be 12px icons at 15% white, which on the light theme is white on
 * white. Across 448 questions between July and September not one person voted
 * either way, so every quality judgement still came from reading threads by
 * hand. It now carries a label and sits at the weight of the other actions in
 * the row: quiet, but legible on both themes.
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

  const base = 'cp-feedback-btn'

  return (
    <div className="cp-feedback">
      <div className="cp-feedback-row">
        {!sent && !failed && <span className="cp-feedback-label">Helpful?</span>}
        <button
          type="button"
          onClick={() => vote('up')}
          aria-label="This answer was helpful"
          aria-pressed={rating === 'up'}
          className={`${base}${rating === 'up' ? ' is-up' : ''}`}
        >
          <ThumbsUp className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => vote('down')}
          aria-label="This answer was not helpful"
          aria-pressed={rating === 'down'}
          className={`${base}${rating === 'down' ? ' is-down' : ''}`}
        >
          <ThumbsDown className="w-4 h-4" />
        </button>
        {sent && <span className="cp-feedback-note">Thanks, noted.</span>}
        {failed && (
          <span className="cp-feedback-note">Could not save that. Your answer is unaffected.</span>
        )}
      </div>

      {askReason && (
        <div className="cp-feedback-reason">
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
            className="cp-feedback-input"
          />
          <button
            type="button"
            onClick={sendReason}
            className="cp-feedback-send"
          >
            Send
          </button>
        </div>
      )}
    </div>
  )
}
