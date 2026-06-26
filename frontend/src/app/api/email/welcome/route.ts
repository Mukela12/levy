import { NextRequest, NextResponse } from 'next/server'
import { sendLevyEmail } from '@/lib/email/resend'
import { renderWelcomeEmail } from '@/lib/email/templates'
import { getAuthenticatedSupabaseUser } from '@/lib/server/supabase-user'

export async function POST(request: NextRequest) {
  try {
    const user = await getAuthenticatedSupabaseUser(request.headers.get('authorization'))
    if (!user?.email) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const payload = await request.json().catch(() => ({}))
    const fullName =
      typeof payload?.fullName === 'string' && payload.fullName.trim()
        ? payload.fullName.trim()
        : user.user_metadata?.full_name || null

    const email = renderWelcomeEmail({ fullName })
    const result = await sendLevyEmail({
      to: [user.email],
      subject: email.subject,
      html: email.html,
      text: email.text,
    })

    return NextResponse.json({ ok: true, id: result.id })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to send welcome email'
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
