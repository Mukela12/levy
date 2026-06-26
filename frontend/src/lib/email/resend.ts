type SendEmailParams = {
  to: string[]
  subject: string
  html: string
  text: string
}

const RESEND_API_URL = 'https://api.resend.com/emails'

function requiredEnv(name: string, fallback?: string) {
  const value = process.env[name] || fallback
  if (!value) throw new Error(`Missing required env: ${name}`)
  return value
}

export async function sendLevyEmail({ to, subject, html, text }: SendEmailParams) {
  const apiKey = requiredEnv('RESEND_API_KEY')
  const from = requiredEnv('LEVY_EMAIL_FROM', 'Mukela Katungu <mukelakatungu@levylegal.ai>')
  const replyTo = requiredEnv('LEVY_EMAIL_REPLY_TO', 'mukelakatungu@levylegal.ai')

  const response = await fetch(RESEND_API_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      from,
      to,
      subject,
      html,
      text,
      reply_to: replyTo,
    }),
    cache: 'no-store',
  })

  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`Resend send failed (${response.status}): ${detail}`)
  }

  return response.json() as Promise<{ id: string }>
}
