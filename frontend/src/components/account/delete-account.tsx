'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Trash2 } from 'lucide-react'
import { useAuth } from '@/components/auth/auth-provider'
import { deleteAccount } from '@/lib/api'
import { SITE_URL, haptic } from '@/lib/native'

export const ACCOUNT_DELETED_KEY = 'levy-account-deleted'

/**
 * Deleting the account from inside the app, as the App Store (5.1.1(v)) and
 * Google Play require. Two steps so it can't happen by accident: open the
 * panel, then type "delete". The server removes the data first and the
 * sign-in last, and a retry after a failure finishes the job.
 */
export function DeleteAccountSection() {
  const { signOut } = useAuth()
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const ready = typed.trim().toLowerCase() === 'delete'

  async function confirm() {
    if (!ready || busy) return
    setBusy(true); setError('')
    try {
      await deleteAccount()
    } catch {
      setError('Your account could not be deleted just now. Nothing is lost by trying again.')
      setBusy(false)
      return
    }
    haptic('success')
    try { sessionStorage.setItem(ACCOUNT_DELETED_KEY, '1') } catch { /* storage off: no notice */ }
    try { await signOut() } catch { /* the account is gone either way */ }
    router.replace('/auth/login')
  }

  return (
    <section className="cp-danger-zone" aria-labelledby="cp-delete-title">
      <h2 id="cp-delete-title">Delete account</h2>
      <p>
        This permanently deletes your chats, uploaded documents, matters and templates, and your sign-in. It can&apos;t
        be undone.{' '}
        <a className="cp-inline-link" href={`${SITE_URL}/support#delete-account`}>What is deleted and kept</a>
      </p>
      {!open ? (
        <button type="button" className="cp-btn danger" onClick={() => { setOpen(true); haptic('medium') }}>
          <Trash2 size={16} />Delete my account
        </button>
      ) : (
        <div className="cp-delete-confirm">
          <label>
            Type delete to confirm
            <input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              autoComplete="off"
              enterKeyHint="done"
              placeholder="delete"
              disabled={busy}
            />
          </label>
          {error && <p role="alert" className="cp-delete-error">{error}</p>}
          <div className="cp-delete-actions">
            <button type="button" className="cp-btn danger solid" onClick={confirm} disabled={!ready || busy}>
              {busy ? 'Deleting…' : 'Delete permanently'}
            </button>
            <button type="button" className="cp-btn" onClick={() => { setOpen(false); setTyped(''); setError('') }} disabled={busy}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
