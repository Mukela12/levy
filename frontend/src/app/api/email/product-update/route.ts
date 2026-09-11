import { NextRequest, NextResponse } from 'next/server'
import { sendLevyEmail } from '@/lib/email/resend'
import { renderCitationUpdateEmail, renderProductUpdateEmail } from '@/lib/email/templates'

/**
 * Second broadcast to the tester list. Same shape as tester-update, with two
 * differences worth knowing before you fire it:
 *
 *  - `preview: true` renders the preview subject, so you can send yourself a
 *    copy first without it looking like the real thing to anyone else.
 *  - `dryRun: true` renders the email and returns the subject plus recipient
 *    count WITHOUT sending. A broadcast is not undoable, so there is a way to
 *    check the list before committing to it.
 */
type ProductUpdateRequest = {
  recipients: string[] | string
  preview?: boolean
  dryRun?: boolean
  /** Which broadcast to render. Defaults to the latest. */
  edition?: keyof typeof EDITIONS
}

// Each broadcast keeps its template, so an old one can still be re-rendered
// for reference. 'case-files' went out 10 August 2026.
const EDITIONS = {
  'case-files': renderProductUpdateEmail,
  citations: renderCitationUpdateEmail,
} as const
const LATEST_EDITION: keyof typeof EDITIONS = 'citations'

// 30 sends at 150ms apart is under 7 a second, comfortably inside Resend's 10.
const SEND_INTERVAL_MS = 150
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

function authorized(request: NextRequest) {
  const expected = process.env.LEVY_EMAIL_ADMIN_TOKEN
  if (!expected) throw new Error('Missing LEVY_EMAIL_ADMIN_TOKEN')
  return request.headers.get('x-levy-email-token') === expected
}

function normalizeRecipients(input: unknown) {
  if (typeof input === 'string') return [input.trim()].filter(Boolean)
  if (!Array.isArray(input)) return []
  const seen = new Set<string>()
  return input
    .filter((item): item is string => typeof item === 'string')
    .map((item) => item.trim().toLowerCase())
    .filter((item) => {
      // De-duplicate: sending the same person two copies of a broadcast is a
      // small thing that reads as carelessness.
      if (!item || !item.includes('@') || seen.has(item)) return false
      seen.add(item)
      return true
    })
}

export async function POST(request: NextRequest) {
  try {
    if (!authorized(request)) {
      return NextResponse.json({ error: 'Forbidden' }, { status: 403 })
    }

    const payload = (await request.json()) as ProductUpdateRequest
    const recipients = normalizeRecipients(payload.recipients)
    if (!recipients.length) {
      return NextResponse.json({ error: 'At least one recipient is required' }, { status: 400 })
    }

    const edition = payload.edition ?? LATEST_EDITION
    if (!Object.hasOwn(EDITIONS, edition)) {
      return NextResponse.json({ error: `Unknown edition: ${edition}` }, { status: 400 })
    }
    const email = EDITIONS[edition]({ preview: Boolean(payload.preview) })

    if (payload.dryRun) {
      return NextResponse.json({
        ok: true,
        dryRun: true,
        edition,
        subject: email.subject,
        wouldSendTo: recipients.length,
        recipients,
      })
    }

    const results: Array<{ email: string; id: string }> = []
    const failures: Array<{ email: string; error: string }> = []

    const send = (recipient: string) =>
      sendLevyEmail({
        to: [recipient],
        subject: email.subject,
        html: email.html,
        text: email.text,
        // Lets Gmail and Apple Mail show their own unsubscribe button, which
        // people use instead of the spam button when it is offered.
        headers: {
          'List-Unsubscribe': `<mailto:${process.env.LEVY_EMAIL_REPLY_TO || 'mukelakatungu@levylegal.ai'}?subject=unsubscribe>`,
        },
      })

    for (const recipient of recipients) {
      try {
        let result
        try {
          result = await send(recipient)
        } catch (error) {
          // Resend allows 10 requests a second. The 11 September send lost 4 of
          // 30 to 429s before the pacing below existed; one retry after the
          // window resets is safe because a 429 means nothing was sent.
          if (!(error instanceof Error && error.message.includes('(429)'))) throw error
          await sleep(1100)
          result = await send(recipient)
        }
        results.push({ email: recipient, id: result.id })
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unknown send failure'
        failures.push({ email: recipient, error: message })
      }
      await sleep(SEND_INTERVAL_MS)
    }

    return NextResponse.json({
      ok: failures.length === 0,
      sent: results.length,
      failed: failures.length,
      results,
      failures,
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to send product update'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
