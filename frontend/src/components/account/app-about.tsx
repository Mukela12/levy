'use client'

import { useEffect, useState } from 'react'
import { ChevronRight, FileText, LifeBuoy, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/components/auth/auth-provider'
import { AiServicesSheet } from '@/components/native/ai-consent'
import { currentAiConsent } from '@/lib/ai-providers'
import { SITE_URL, openInBrowser } from '@/lib/native'

/**
 * The app's About block in Account: the privacy policy, the AI services and
 * what was agreed, help and a way to reach a person (the website's /support
 * page), and the version (store reviewers and support both ask for it).
 */
export function AppAbout() {
  const { user } = useAuth()
  const [version, setVersion] = useState('')
  const [reviewing, setReviewing] = useState(false)
  const consent = currentAiConsent(user?.user_metadata)

  useEffect(() => {
    void import('@capacitor/app')
      .then(({ App }) => App.getInfo())
      .then((info) => setVersion(`${info.version} (${info.build})`))
      .catch(() => {})
  }, [])

  return (
    <section className="cp-about" aria-labelledby="cp-about-title">
      <h2 id="cp-about-title">About Levy</h2>
      <ul className="cp-about-list">
        <li>
          <button type="button" onClick={() => setReviewing(true)}>
            <ShieldCheck size={18} aria-hidden="true" />
            <span>AI services and your data</span>
            <ChevronRight size={16} aria-hidden="true" />
          </button>
        </li>
        <li>
          <button type="button" onClick={() => openInBrowser(`${SITE_URL}/privacy`)}>
            <FileText size={18} aria-hidden="true" />
            <span>Privacy policy</span>
            <ChevronRight size={16} aria-hidden="true" />
          </button>
        </li>
        <li>
          <button type="button" onClick={() => openInBrowser(`${SITE_URL}/support`)}>
            <LifeBuoy size={18} aria-hidden="true" />
            <span>Help and support</span>
            <ChevronRight size={16} aria-hidden="true" />
          </button>
        </li>
      </ul>
      <p className="cp-about-note">
        Levy gives legal information, not legal advice. For advice on your situation, speak to an advocate.
        {version && <><br />Version {version}</>}
      </p>
      {reviewing && <AiServicesSheet mode="review" consent={consent} onClose={() => setReviewing(false)} />}
    </section>
  )
}
