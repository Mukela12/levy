import type { Metadata } from 'next'
import Link from 'next/link'
import { SITE_URL } from '@/lib/server/corpus'
import { ADDRESS, OPERATOR, SUPPORT_EMAIL, SUPPORT_PHONE } from '@/lib/contact'

// The support address the App Store and Google Play listings point at. Its
// #delete-account section is also the account-deletion link Google Play asks
// for: it names the app and the developer, gives the steps, and says what is
// deleted and what is kept. Keep it in step with
// backend/app/services/account_deletion.py and the privacy policy.
const UPDATED = '10 November 2026'

export const metadata: Metadata = {
  title: 'Help and support',
  description: 'Get help with Levy, reach the team, and delete your account and everything in it.',
  alternates: { canonical: `${SITE_URL}/support` },
}

function Section({ id, title, children }: { id?: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="mt-8 scroll-mt-20">
      <h2 className="text-[17px] font-semibold text-white/85">{title}</h2>
      <div className="mt-2 space-y-2 text-[14px] leading-relaxed text-white/65">{children}</div>
    </section>
  )
}

function Question({ q, children }: { q: string; children: React.ReactNode }) {
  return (
    <div className="pt-3">
      <h3 className="text-[14.5px] font-medium text-white/80">{q}</h3>
      <div className="mt-1">{children}</div>
    </div>
  )
}

const link = 'text-emerald-300 underline underline-offset-2 hover:text-emerald-200'

export default function SupportPage() {
  const mail = `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent('Levy help')}`
  const deleteMail = `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent('Delete my account')}`
  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <h1 className="text-[26px] font-semibold text-white/90 tracking-tight">Help and support</h1>
      <p className="text-[13px] text-white/45 mt-2">For the Levy website and the Levy apps for iPhone and Android. Last updated {UPDATED}</p>

      <Section title="Contact us">
        <p>
          Email <a className={link} href={mail}>{SUPPORT_EMAIL}</a> or call {SUPPORT_PHONE}. Tell us the email address
          on your account and, if it is about an answer, the question you asked.
        </p>
      </Section>

      <Section title="Common questions">
        <Question q="I can't sign in">
          <p>
            On the sign-in screen, choose <strong className="text-white/80">Forgot password</strong>. The email has a link
            to set a new password. After that, sign in with the new password on the website or in the app.
          </p>
        </Question>
        <Question q="Where are my chats?">
          <p>
            Chats are saved to your account. Open the menu and look under <strong className="text-white/80">Recent</strong>,
            on any phone or computer where you are signed in with the same email.
          </p>
        </Question>
        <Question q="An answer looks wrong">
          <p>
            Under every answer, the thumbs down lets you say what was wrong, and in the app the flag reports an answer that
            is harmful, offensive or wrong about the law. Levy gives legal information, not legal
            advice: check the cited section, and speak to an advocate about your own situation.
          </p>
        </Question>
        <Question q="Which companies see my questions?">
          <p>
            The AI services that write and search for answers are listed, with their countries, in the{' '}
            <Link className={link} href="/privacy">privacy policy</Link>. In the app the same list is under Account, About
            Levy, AI services and your data.
          </p>
        </Question>
      </Section>

      <Section id="delete-account" title="Delete your Levy account">
        <p>You can delete your account yourself at any time. It takes effect straight away and can&apos;t be undone.</p>
        <ol className="list-decimal pl-5 space-y-1.5">
          <li>Sign in to the Levy app or the website and open <strong className="text-white/80">Account</strong> (Your account).</li>
          <li>Under <strong className="text-white/80">Delete account</strong>, choose Delete my account.</li>
          <li>Type <strong className="text-white/80">delete</strong> and choose Delete permanently.</li>
        </ol>
        <p>
          <strong className="text-white/80">What is deleted:</strong> your sign-in (email address, password and name), your
          chats and Levy&apos;s answers, documents you uploaded and their files, your matters and templates, drafts Levy
          made for you, and your feedback and reports.
        </p>
        <p>
          <strong className="text-white/80">What is kept:</strong> nothing that identifies you. Copies in our database
          backups are gone within 30 days, as those backups are replaced. Legislation you did not upload stays in the
          shared library.
        </p>
        <p>
          <strong className="text-white/80">Can&apos;t sign in?</strong> Email{' '}
          <a className={link} href={deleteMail}>{SUPPORT_EMAIL}</a> from the address on your account with the subject
          &quot;Delete my account&quot;. We delete it within 30 days.
        </p>
      </Section>

      <Section title="Who runs Levy">
        <p>Levy is operated by {OPERATOR}, {ADDRESS}.</p>
      </Section>
    </div>
  )
}
