import { NextRequest, NextResponse } from 'next/server'
import { sendLevyEmail } from '@/lib/email/resend'
import { LEVY_OPERATOR, renderFirmOutreachEmail, type FirmPractice, type OutreachDraft } from '@/lib/email/templates'

/**
 * Demo invitations to law firms, one personalised email each (firm name,
 * published contact, a line for the firm's main practice). Same guard rails
 * as product-update: the admin token, `dryRun` to render every subject and
 * check the list without sending, pacing inside Resend's 10 a second, and a
 * List-Unsubscribe header. Only addresses a firm publishes for enquiries go
 * on the list (levy-research/leads); an opt-out is honoured by never sending
 * again.
 *
 * The ECT Act 2021 allows one unsolicited commercial email per person
 * (s.65(1)) and wants every one to carry the sender's place of business and
 * phone, where the address was found, and the privacy policy (s.64(2)). A
 * real send therefore refuses to run without the operator's details
 * (LEVY_OPERATOR, overridable by LEVY_BUSINESS_* env vars), without a source
 * for every recipient, or while levylegal.ai/privacy is not live.
 */
type Recipient = {
  email: string
  firm: string
  contactName?: string | null
  practice?: FirmPractice
  hook?: string | null
  source?: string | null
  sourceDate?: string | null
}

type OutreachRequest = {
  recipients: Recipient[]
  variant?: 'a' | 'b' | 'split'
  /** Wording: 'formal' (the chosen draft) unless another is named. */
  draft?: OutreachDraft
  preview?: boolean
  dryRun?: boolean
}

const PRACTICES = new Set<FirmPractice>(['litigation', 'employment', 'corporate', 'general'])
const DRAFTS = new Set<OutreachDraft>(['demo', 'feedback', 'short', 'story', 'formal'])
const SEND_INTERVAL_MS = 200
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

function authorized(request: NextRequest) {
  const expected = process.env.LEVY_EMAIL_ADMIN_TOKEN
  if (!expected) throw new Error('Missing LEVY_EMAIL_ADMIN_TOKEN')
  return request.headers.get('x-levy-email-token') === expected
}

function clean(input: unknown): Recipient[] {
  if (!Array.isArray(input)) return []
  const seen = new Set<string>()
  const out: Recipient[] = []
  for (const item of input) {
    if (!item || typeof item !== 'object') continue
    const r = item as Record<string, unknown>
    const email = typeof r.email === 'string' ? r.email.trim().toLowerCase() : ''
    const firm = typeof r.firm === 'string' ? r.firm.trim().slice(0, 120) : ''
    if (!email.includes('@') || !firm || seen.has(email)) continue
    seen.add(email)
    const practice = typeof r.practice === 'string' && PRACTICES.has(r.practice as FirmPractice)
      ? (r.practice as FirmPractice) : 'general'
    const text = (v: unknown, max: number) => (typeof v === 'string' && v.trim() ? v.trim().slice(0, max) : null)
    out.push({
      email, firm, practice,
      contactName: text(r.contactName, 80),
      hook: text(r.hook, 240),
      source: text(r.source, 160),
      sourceDate: text(r.sourceDate, 40),
    })
  }
  return out
}

export async function POST(request: NextRequest) {
  try {
    if (!authorized(request)) {
      return NextResponse.json({ error: 'Forbidden' }, { status: 403 })
    }
    const payload = (await request.json()) as OutreachRequest
    const recipients = clean(payload.recipients)
    if (!recipients.length) {
      return NextResponse.json({ error: 'At least one recipient with an email and a firm is required' }, { status: 400 })
    }
    const sender = {
      business: process.env.LEVY_BUSINESS_NAME || LEVY_OPERATOR.business,
      address: process.env.LEVY_BUSINESS_ADDRESS || LEVY_OPERATOR.address,
      phone: process.env.LEVY_BUSINESS_PHONE || LEVY_OPERATOR.phone,
      logoUrl: LEVY_OPERATOR.logoUrl,
    }
    // 'split' alternates the two subject lines so their open rates can be compared.
    const variantFor = (i: number): 'a' | 'b' =>
      payload.variant === 'b' ? 'b' : payload.variant === 'split' ? (i % 2 ? 'b' : 'a') : 'a'
    const emails = recipients.map((r, i) => ({
      recipient: r,
      variant: variantFor(i),
      email: renderFirmOutreachEmail({
        firm: r.firm, contactName: r.contactName, practice: r.practice, hook: r.hook,
        source: r.source, sourceDate: r.sourceDate, sender,
        variant: variantFor(i), preview: Boolean(payload.preview),
        draft: DRAFTS.has(payload.draft as OutreachDraft) ? payload.draft : 'formal',
      }),
    }))

    if (payload.dryRun) {
      return NextResponse.json({
        ok: true,
        dryRun: true,
        wouldSendTo: emails.length,
        emails: emails.map(({ recipient, variant, email }) => ({
          to: recipient.email, firm: recipient.firm, practice: recipient.practice, variant, subject: email.subject,
          source: recipient.source, hook: recipient.hook,
        })),
      })
    }

    // A preview goes only to Levy's own inbox, with placeholders showing.
    if (!payload.preview) {
      const missing = [
        ...(['business', 'address', 'phone'] as const).filter((k) => !sender[k]?.trim()).map((k) => `LEVY_BUSINESS_${k.toUpperCase()}`),
        ...recipients.filter((r) => !r.source).map((r) => `a source for ${r.email}`),
      ]
      const privacy = await fetch(`${process.env.NEXT_PUBLIC_SITE_URL || 'https://levylegal.ai'}/privacy`, { method: 'HEAD' })
        .then((r) => r.ok).catch(() => false)
      if (!privacy) missing.push('a live privacy policy at /privacy')
      if (missing.length) {
        return NextResponse.json({ error: `Not sent. The ECT Act needs: ${missing.join(', ')}` }, { status: 400 })
      }
    }

    const results: Array<{ email: string; firm: string; variant: string; id: string }> = []
    const failures: Array<{ email: string; error: string }> = []
    for (const { recipient, variant, email } of emails) {
      const send = () => sendLevyEmail({
        to: [recipient.email],
        subject: email.subject,
        html: email.html,
        text: email.text,
        headers: {
          'List-Unsubscribe': `<mailto:${process.env.LEVY_EMAIL_REPLY_TO || 'mukelakatungu@levylegal.ai'}?subject=no%20thanks>`,
        },
      })
      try {
        let result
        try {
          result = await send()
        } catch (error) {
          if (!(error instanceof Error && error.message.includes('(429)'))) throw error
          await sleep(1100)
          result = await send()
        }
        results.push({ email: recipient.email, firm: recipient.firm, variant, id: result.id })
      } catch (error) {
        failures.push({ email: recipient.email, error: error instanceof Error ? error.message : 'Unknown send failure' })
      }
      await sleep(SEND_INTERVAL_MS)
    }
    return NextResponse.json({ ok: failures.length === 0, sent: results.length, failed: failures.length, results, failures })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to send firm outreach'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
