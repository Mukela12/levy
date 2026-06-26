'use client'

/**
 * Interactive quiz / mock-exam card produced by the `generate_quiz` tool in
 * Study Mode. The student selects an answer per question, submits, and gets
 * graded instantly with the correct answer, an explanation, and a citation
 * for each question. "Retake" resets the attempt. Questions are grounded in
 * the corpus + case law server-side; this component only handles the attempt.
 */

import { useState } from 'react'
import { GraduationCap, Check, X, RotateCcw, BookMarked } from 'lucide-react'
import type { Quiz } from '@/lib/api'

const LETTERS = ['A', 'B', 'C', 'D', 'E', 'F']

export function QuizCard({ quiz }: { quiz: Quiz }) {
  const [answers, setAnswers] = useState<Record<number, number>>({})
  const [submitted, setSubmitted] = useState(false)
  const questions = quiz.questions ?? []
  const total = questions.length
  const answeredCount = Object.keys(answers).length
  const score = submitted
    ? questions.reduce((n, q, i) => (answers[i] === q.correct_index ? n + 1 : n), 0)
    : 0

  function choose(qi: number, oi: number) {
    if (submitted) return
    setAnswers((a) => ({ ...a, [qi]: oi }))
  }
  function reset() {
    setAnswers({})
    setSubmitted(false)
  }

  const pct = total ? Math.round((score / total) * 100) : 0
  const scoreTone =
    pct >= 70 ? 'text-emerald-300' : pct >= 50 ? 'text-amber-300' : 'text-rose-300'

  return (
    <div data-testid="quiz-card" className="my-3 -mx-1 rounded-xl border border-emerald-500/15 bg-emerald-500/[0.025] overflow-hidden">
      <div className="flex items-center gap-2 px-3.5 py-2.5 border-b border-emerald-500/[0.08]">
        <span className="flex items-center justify-center size-6 rounded-md bg-emerald-500/10">
          <GraduationCap size={13} className="text-emerald-400" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] uppercase tracking-wider text-emerald-300/80">Quiz</div>
          <div className="text-[13px] text-white/85 font-medium truncate mt-0.5">{quiz.title}</div>
        </div>
        {submitted && (
          <span className={`text-[13px] font-semibold tabular-nums ${scoreTone}`}>
            {score}/{total}
          </span>
        )}
      </div>

      <div className="p-3.5 space-y-4">
        {questions.map((q, qi) => {
          const chosen = answers[qi]
          return (
            <div key={qi}>
              <div className="text-[13px] text-white/85 font-medium leading-snug mb-2">
                <span className="text-emerald-400/70">{qi + 1}.</span> {q.stem}
              </div>
              <div className="space-y-1.5">
                {q.options.map((opt, oi) => {
                  const isChosen = chosen === oi
                  const isCorrect = q.correct_index === oi
                  let cls = 'border-white/[0.08] bg-white/[0.02] hover:bg-white/[0.04] text-white/75'
                  if (submitted) {
                    if (isCorrect) cls = 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100'
                    else if (isChosen) cls = 'border-rose-500/40 bg-rose-500/10 text-rose-100'
                    else cls = 'border-white/[0.06] bg-transparent text-white/40'
                  } else if (isChosen) {
                    cls = 'border-emerald-500/40 bg-emerald-500/10 text-white/90'
                  }
                  return (
                    <button
                      key={oi}
                      type="button"
                      data-testid={`quiz-option-${qi}`}
                      onClick={() => choose(qi, oi)}
                      disabled={submitted}
                      className={`w-full flex items-start gap-2.5 px-2.5 py-2 rounded-lg border text-left text-[12.5px] leading-snug transition-colors ${cls} ${submitted ? 'cursor-default' : 'cursor-pointer'}`}
                    >
                      <span className="shrink-0 mt-px text-[11px] font-semibold opacity-70 w-3.5">{LETTERS[oi]}</span>
                      <span className="flex-1">{opt}</span>
                      {submitted && isCorrect && <Check size={14} className="shrink-0 text-emerald-400 mt-px" />}
                      {submitted && isChosen && !isCorrect && <X size={14} className="shrink-0 text-rose-400 mt-px" />}
                    </button>
                  )
                })}
              </div>
              {submitted && (q.explanation || q.citation) && (
                <div className="mt-2 rounded-lg bg-white/[0.03] border border-white/[0.06] px-2.5 py-2">
                  {q.explanation && (
                    <p className="text-[11.5px] text-white/60 leading-snug">{q.explanation}</p>
                  )}
                  {q.citation && (
                    <div className="flex items-center gap-1.5 mt-1 text-[10.5px] text-emerald-400/60">
                      <BookMarked size={11} /> {q.citation}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="border-t border-emerald-500/[0.08] px-3.5 py-2.5 flex items-center justify-between gap-2 bg-black/20">
        {!submitted ? (
          <>
            <span className="text-[11px] text-white/35">{answeredCount}/{total} answered</span>
            <button
              type="button"
              data-testid="quiz-submit"
              onClick={() => setSubmitted(true)}
              disabled={answeredCount === 0}
              className="px-3 py-1.5 rounded-lg text-[12px] font-medium bg-emerald-500/15 border border-emerald-500/30 text-emerald-200 hover:bg-emerald-500/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Submit answers
            </button>
          </>
        ) : (
          <>
            <span data-testid="quiz-score" className="text-[11.5px] text-white/55">
              You scored <span className={`font-semibold ${scoreTone}`}>{score} of {total}</span> ({pct}%)
            </span>
            <button
              type="button"
              onClick={reset}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-medium text-white/60 hover:text-white/90 border border-white/[0.10] hover:bg-white/[0.04] transition-colors"
            >
              <RotateCcw size={12} /> Retake
            </button>
          </>
        )}
      </div>
    </div>
  )
}
