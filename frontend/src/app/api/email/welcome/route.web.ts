import { NextRequest, NextResponse } from 'next/server'
import { sendLevyEmail } from '@/lib/email/resend'
import { renderWelcomeEmail } from '@/lib/email/templates'
import { getAuthenticatedSupabaseUser } from '@/lib/server/supabase-user'

// The iOS and Android apps call this route from their own origins after a
// sign-up. The route authenticates with the bearer token, not cookies.
const APP_ORIGINS = new Set(['capacitor://localhost', 'https://localhost'])

function cors(request: NextRequest): Record<string, string> {
  const origin = request.headers.get('origin') || ''
  if (!APP_ORIGINS.has(origin)) return {}
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Authorization, Content-Type',
    Vary: 'Origin',
  }
}

export function OPTIONS(request: NextRequest) {
  return new NextResponse(null, { status: 204, headers: cors(request) })
}

export async function POST(request: NextRequest) {
  const headers = cors(request)
  try {
    const user = await getAuthenticatedSupabaseUser(request.headers.get('authorization'))
    if (!user?.email) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401, headers })
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

    return NextResponse.json({ ok: true, id: result.id }, { headers })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to send welcome email'
    return NextResponse.json({ error: message }, { status: 500, headers })
  }
}
