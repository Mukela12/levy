import { NextRequest, NextResponse } from 'next/server'
import { sendLevyEmail } from '@/lib/email/resend'
import { renderTesterAnnouncementEmail } from '@/lib/email/templates'

type TesterUpdateRequest = {
  recipients: string[] | string
  preview?: boolean
}

function authorized(request: NextRequest) {
  const expected = process.env.LEVY_EMAIL_ADMIN_TOKEN
  if (!expected) throw new Error('Missing LEVY_EMAIL_ADMIN_TOKEN')
  return request.headers.get('x-levy-email-token') === expected
}

function normalizeRecipients(input: unknown) {
  if (typeof input === 'string') return [input.trim()].filter(Boolean)
  if (!Array.isArray(input)) return []
  return input
    .filter((item): item is string => typeof item === 'string')
    .map((item) => item.trim())
    .filter(Boolean)
}

export async function POST(request: NextRequest) {
  try {
    if (!authorized(request)) {
      return NextResponse.json({ error: 'Forbidden' }, { status: 403 })
    }

    const payload = (await request.json()) as TesterUpdateRequest
    const recipients = normalizeRecipients(payload.recipients)
    if (!recipients.length) {
      return NextResponse.json({ error: 'At least one recipient is required' }, { status: 400 })
    }

    const email = renderTesterAnnouncementEmail({ preview: Boolean(payload.preview) })
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
    const message = error instanceof Error ? error.message : 'Failed to send tester update'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
