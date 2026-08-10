import { NextRequest, NextResponse } from 'next/server'
import { sendLevyEmail } from '@/lib/email/resend'
import { renderProductUpdateEmail } from '@/lib/email/templates'

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
}

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

    const email = renderProductUpdateEmail({ preview: Boolean(payload.preview) })

    if (payload.dryRun) {
      return NextResponse.json({
        ok: true,
        dryRun: true,
        subject: email.subject,
        wouldSendTo: recipients.length,
        recipients,
      })
    }

    const results: Array<{ email: string; id: string }> = []
    const failures: Array<{ email: string; error: string }> = []

    for (const recipient of recipients) {
      try {
        const result = await sendLevyEmail({
          to: [recipient],
          subject: email.subject,
          html: email.html,
          text: email.text,
        })
        results.push({ email: recipient, id: result.id })
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unknown send failure'
        failures.push({ email: recipient, error: message })
      }
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
