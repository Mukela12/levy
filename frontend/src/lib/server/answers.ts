import 'server-only'
import data from '@/data/answers.json'

export interface AnswerSource {
  act: string
  section: string
  document_id?: string | null
}

export interface Answer {
  slug: string
  category: string
  question: string
  answer: string
  sources: AnswerSource[]
}

export const answers = data as Answer[]

export function getAnswer(slug: string): Answer | null {
  return answers.find((a) => a.slug === slug) ?? null
}

export function answersByCategory(): [string, Answer[]][] {
  const map = new Map<string, Answer[]>()
  for (const a of answers) {
    if (!map.has(a.category)) map.set(a.category, [])
    map.get(a.category)!.push(a)
  }
  return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]))
}
