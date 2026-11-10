'use client'

import { useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { useAuth } from '@/components/auth/auth-provider'
import { createClient } from '@/lib/supabase'
import { AI_CONSENT_VERSION, AI_PROVIDERS, type AiConsentRecord } from '@/lib/ai-providers'
import { SITE_URL, haptic, openInBrowser } from '@/lib/native'

function formatDate(iso: string) {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })
}

/**
 * Names the AI services Levy sends questions and documents to, and asks for
 * permission before the first question (App Store guideline 5.1.2(i)). The
 * answer is saved on the account, so it is asked once per person, not once
 * per phone. In review mode (from Account) it shows what was agreed.
 */
export function AiServicesSheet({ mode, consent, onClose }: {
  mode: 'checking' | 'ask' | 'review'
  consent?: AiConsentRecord | null
  onClose?: () => void
}) {
  const { signOut } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function agree() {
    if (busy) return
    setBusy(true); setError('')
    try {
      const record: AiConsentRecord = { version: AI_CONSENT_VERSION, at: new Date().toISOString() }
      const { error: failed } = await createClient().auth.updateUser({ data: { ai_consent: record } })
      if (failed) throw failed
      haptic('success')
    } catch {
      setError('That could not be saved. Check your connection and try again.')
      setBusy(false)
    }
  }

  // While the account is being checked, hold the screen without content so
  // nothing can be asked before the answer is known, and nothing flashes.
  if (mode === 'checking') return <div className="cp-consent" aria-busy="true" />

  return (
    <div className="cp-consent" role="dialog" aria-modal="true" aria-labelledby="cp-consent-title">
      <div className="cp-consent-body">
        <span className="cp-consent-mark" aria-hidden="true"><ShieldCheck size={22} /></span>
        <span className="cp-eyebrow">{mode === 'ask' ? 'Before your first question' : 'AI services'}</span>
        <h1 id="cp-consent-title">How Levy answers you</h1>
        <p>
          Levy is built on AI services run by other companies. To answer, it sends your question, the conversation so
          far and any document you attach to the services below. None of them is in Zambia.
        </p>
        <ul className="cp-consent-list">
          {AI_PROVIDERS.map((p) => (
            <li key={p.name}>
              <strong>{p.name}</strong>
              <span>{p.what}</span>
              <small>{p.where}</small>
            </li>
          ))}
        </ul>
        <p className="cp-consent-small">
          Anthropic does not train its models on Levy&apos;s data and deletes it within 30 days, unless it is flagged for
          misuse. OpenAI does not train on API data and keeps abuse-monitoring logs for up to 30 days. Web searches go to
          Tavily only when you turn Web on.
        </p>
        <button type="button" className="cp-consent-link" onClick={() => openInBrowser(`${SITE_URL}/privacy`)}>
          Read the privacy policy
        </button>
        {mode === 'review' && consent && (
          <p className="cp-consent-small">You agreed to this on {formatDate(consent.at)}. To withdraw, delete your account in Account, or email us from the privacy policy.</p>
        )}
        {error && <p role="alert" className="cp-consent-error">{error}</p>}
      </div>
      <div className="cp-consent-actions">
        {mode === 'ask' ? (
          <>
            <button type="button" className="cp-btn primary" onClick={agree} disabled={busy}>
              {busy ? 'Saving…' : 'Agree and continue'}
            </button>
            <button type="button" className="cp-btn ghost" onClick={() => { void signOut() }} disabled={busy}>
              Not now, sign out
            </button>
          </>
        ) : (
          <button type="button" className="cp-btn primary" onClick={onClose}>Done</button>
        )}
      </div>
    </div>
  )
}
