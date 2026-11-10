import { NextRequest, NextResponse } from 'next/server'
import { sendLevyEmail } from '@/lib/email/resend'

/**
 * Deliver a scheduled ops report by email.
 *
 * Why this exists: the 12 August scheduled check ran exactly on time and was
 * still useless, because a cloud routine's output lands in a session at
 * claude.ai/code/routines that nobody opens. A report that fires perfectly and
 * is never read is the same as no report.
 *
 * Deliberately narrow:
 *  - The RECIPIENT IS FIXED server-side. It is not a caller parameter, so this
 *    can never be turned into a way to mail arbitrary people. A leaked token
 *    lets someone send mail to the owner, and nothing else.
 *  - Plain text only. No HTML, no templates, no links to render.
 *  - Gated by ADMIN_STATS_TOKEN, the same read-only token the scheduled report
 *    already carries, so the routine holds ONE secret rather than two. It is
 *    scoped to ops reporting and grants nothing destructive.
 */

const REPORT_TO = process.env.LEVY_OPS_REPORT_TO || 'mukelakatungu@levylegal.ai'

type OpsReportRequest = {
  subject?: string
  body: string
}

export async function POST(request: NextRequest) {
  try {
    const expected = (process.env.ADMIN_STATS_TOKEN || '').trim()
    if (!expected) {
      // Unset token means the endpoint does not exist, so it cannot be left
      // accidentally open.
      return NextResponse.json({ error: 'Not found' }, { status: 404 })
    }
    const supplied = (request.headers.get('x-levy-ops-token') || '').trim()
    if (!supplied || supplied !== expected) {
      return NextResponse.json({ error: 'Forbidden' }, { status: 403 })
    }

    const payload = (await request.json()) as OpsReportRequest
    const body = (payload?.body || '').trim()
    if (!body) {
      return NextResponse.json({ error: 'body is required' }, { status: 400 })
    }

    const subject = (payload.subject || 'Levy ops report').slice(0, 200)
    const result = await sendLevyEmail({
      to: [REPORT_TO],
      subject,
      // Wrapped in <pre> so a monospace report keeps its alignment in a mail
      // client rather than collapsing into a paragraph.
      html: `<pre style="font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px;line-height:1.6;white-space:pre-wrap;">${body
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')}</pre>`,
      text: body.slice(0, 100_000),
    })

    return NextResponse.json({ ok: true, id: result.id, to: REPORT_TO })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to send ops report'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
