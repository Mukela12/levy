import { listActs, SITE_URL } from '@/lib/server/corpus'
import { answers } from '@/lib/server/answers'

export const revalidate = 86400

/**
 * /llms.txt — the emerging convention that points AI answer engines
 * (ChatGPT, Perplexity, Claude, Google AI) at the site's key content so they
 * can discover and cite it. We expose the public Acts directory generated from
 * the corpus. Private app routes are intentionally omitted.
 */
export async function GET() {
  let actsBlock = ''
  try {
    const acts = await listActs()
    actsBlock = acts
      .map((a) => `- [${a.name}${a.year ? ` (${a.year})` : ''}](${SITE_URL}/acts/${a.slug})`)
      .join('\n')
  } catch {
    actsBlock = `- [All Acts](${SITE_URL}/acts)`
  }

  const body = `# Levy

> Levy is a free AI legal assistant for Zambian law. It answers questions grounded in actual Zambian legislation and case law, with citations to the Acts and judgments. It also helps law and bar (ZIALE) students learn, with lessons, exam cheat sheets and graded quizzes.

## Key pages
- [Ask Levy](${SITE_URL}/chat): ask any question about Zambian law and get a cited answer
- [Common questions answered](${SITE_URL}/answers): plain-English answers to common Zambian legal questions, with citations
- [Acts of Parliament of Zambia](${SITE_URL}/acts): directory of Zambian Acts, each with its sections
- [Study mode](${SITE_URL}/study): learn a topic, generate an exam cheat sheet, or take a graded quiz

## Common Zambian law questions
${answers.map((a) => `- [${a.question}](${SITE_URL}/answers/${a.slug})`).join('\n')}

## Acts of Parliament of Zambia
${actsBlock}

## Notes
- Jurisdiction: Republic of Zambia.
- Levy provides legal information, not legal advice.
`

  return new Response(body, {
    headers: { 'content-type': 'text/plain; charset=utf-8' },
  })
}
