'use client'

/**
 * The clarifying-question card. Levy hands the turn back with exactly one
 * question; this card makes answering it one tap (choice chips) or one short
 * reply. When the thread has moved on the card renders quietly as a record
 * of what was asked.
 */

import { useState } from 'react'
import { ArrowUp, CornerDownRight } from 'lucide-react'

export interface QuestionCardProps {
  question: string
  options?: string[]
  allowFreeText?: boolean
  /** Present only while this is the latest turn; absent renders read-only. */
  onAnswer?: (text: string) => void
}

export function QuestionCard({ question, options = [], allowFreeText = true, onAnswer }: QuestionCardProps) {
  const [text, setText] = useState('')
  const [sent, setSent] = useState<string | null>(null)
  const live = Boolean(onAnswer) && !sent

  function answer(value: string) {
    const v = value.trim()
    if (!v || !onAnswer) return
    setSent(v)
    onAnswer(v)
  }

  return (
    <div className={'cp-question-card' + (live ? '' : ' is-settled')} role="group" aria-label="Levy needs one answer">
      <div className="cp-question-eyebrow">
        <CornerDownRight size={14} aria-hidden="true" />
        <span>Levy needs one answer to continue</span>
      </div>
      <p className="cp-question-text">{question}</p>
      {options.length > 0 && (
        <div className="cp-question-options" role="list">
          {options.map((o) => (
            <button key={o} type="button" role="listitem" disabled={!live} className={'cp-question-option' + (sent === o ? ' is-chosen' : '')} onClick={() => answer(o)}>
              {o}
            </button>
          ))}
        </div>
      )}
      {allowFreeText && live && (
        <form
          className="cp-question-input"
          onSubmit={(e) => {
            e.preventDefault()
            answer(text)
          }}
        >
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={options.length ? 'Or type your own answer…' : 'Type your answer…'}
            aria-label="Your answer"
          />
          <button type="submit" aria-label="Send answer" disabled={!text.trim()}>
            <ArrowUp size={16} />
          </button>
        </form>
      )}
      {!live && !sent && <p className="cp-question-hint">Answered below, or reply in the box to continue.</p>}
    </div>
  )
}
