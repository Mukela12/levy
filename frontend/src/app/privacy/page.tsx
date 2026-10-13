import type { Metadata } from 'next'
import { SITE_URL } from '@/lib/server/corpus'

// The ECT Act 2021 s.64(2)(d) wants every marketing email to point here, and
// the Data Protection Act 2021 wants people told who holds their data, where
// it goes and how to object. Keep the sub-processor table in step with the
// services the backend actually calls (backend/app/config.py keys).
const OPERATOR = 'Fluxium Tech Business, the trading name of Mukela Katungu (TPIN 2003851084)'
const ADDRESS = 'Kulima Tower, 11th Floor, Room 1107, Lusaka, Zambia'
const PHONE = '+260 771 699 187'
const EMAIL = 'mukelakatungu@levylegal.ai'
const UPDATED = '12 October 2026'

export const metadata: Metadata = {
  title: 'Privacy policy',
  description: 'What Levy collects, why, who processes it and where, how long it is kept, and your rights under the Data Protection Act 2021.',
  alternates: { canonical: `${SITE_URL}/privacy` },
}

const PROCESSORS: Array<[string, string, string]> = [
  ['Anthropic', 'Writes answers and drafts (Claude models)', 'United States'],
  ['OpenAI', 'Turns questions and uploaded documents into search vectors', 'United States'],
  ['Google (Gemini API)', 'Backup search vectors when OpenAI is unavailable', 'United States'],
  ['Moonshot AI and OpenRouter', 'Backup answer models when Anthropic is unavailable', 'China and the United States'],
  ['Tavily', 'Web searches when Levy looks beyond its library', 'United States'],
  ['Supabase', 'Database, sign-in and file storage', 'United States (North Virginia)'],
  ['Railway', "Runs Levy's server", 'Singapore'],
  ['Vercel', 'Hosts the website; page-view and speed analytics without advertising cookies', 'United States'],
  ['Cloudflare', 'Bot check (Turnstile)', 'Global network'],
  ['Resend', 'Sends email', 'United States'],
]

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-[17px] font-semibold text-white/85">{title}</h2>
      <div className="mt-2 space-y-2 text-[14px] leading-relaxed text-white/65">{children}</div>
    </section>
  )
}

export default function PrivacyPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <h1 className="text-[26px] font-semibold text-white/90 tracking-tight">Privacy policy</h1>
      <p className="text-[13px] text-white/45 mt-2">Last updated {UPDATED}</p>

      <Section title="Who we are">
        <p>
          Levy (levylegal.ai) is a Zambian legal research and drafting tool operated by {OPERATOR}, {ADDRESS}.
          Email {EMAIL}, phone {PHONE}. Fluxium Tech Business is the data controller for the personal data
          described here, and Mukela Katungu is its data protection contact.
        </p>
      </Section>

      <Section title="What we collect">
        <ul className="list-disc pl-5 space-y-1.5">
          <li><strong className="text-white/80">Your account:</strong> email address, a password stored only as a hash by our sign-in provider, any name you give us, and how you found Levy (campaign tags, the referring website and the page you landed on).</li>
          <li><strong className="text-white/80">What you ask and upload:</strong> your questions, Levy&apos;s answers, your chat history, documents you upload, your matters and templates, and any feedback you give.</li>
          <li><strong className="text-white/80">If you use Levy without an account:</strong> your question is answered but not saved as a chat. We keep a record without its content (the time, a one-way hash of your IP address, whether sources were found, how long the answer took and how you found Levy) to run the free-question limit and count use.</li>
          <li><strong className="text-white/80">Technical data:</strong> IP address, browser type and request logs kept by our hosting providers, page-view analytics without advertising cookies, and a bot check when you sign up or ask as a guest.</li>
          <li><strong className="text-white/80">In your browser:</strong> how you arrived (for signup attribution), a question waiting to be sent, and display settings, kept in local storage on your device.</li>
        </ul>
        <p>
          Please do not put client names, NRC numbers, health details or other sensitive information into Levy unless you
          need to. Use initials and leave identifiers out.
        </p>
      </Section>

      <Section title="Why we use it">
        <ul className="list-disc pl-5 space-y-1.5">
          <li>To answer your questions, draft documents and keep your history so you can return to it.</li>
          <li>To check and improve Levy&apos;s answers. We review samples of questions and answers to find mistakes.</li>
          <li>To run the free-question limit and keep Levy secure, including stopping abuse.</li>
          <li>To email you about your account and, if you have an account, about changes to Levy. You can opt out of product emails at any time.</li>
        </ul>
        <p>We do not sell personal data, and we do not use it for advertising.</p>
      </Section>

      <Section title="Who processes it, and where">
        <p>Levy uses these services to run. Each receives only what it needs for its task.</p>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px] mt-1">
            <thead className="text-white/50">
              <tr><th className="py-1.5 pr-3 font-medium">Service</th><th className="py-1.5 pr-3 font-medium">What it does</th><th className="py-1.5 font-medium">Where</th></tr>
            </thead>
            <tbody>
              {PROCESSORS.map(([name, what, where]) => (
                <tr key={name} className="border-t border-white/[0.06]">
                  <td className="py-1.5 pr-3 text-white/75">{name}</td>
                  <td className="py-1.5 pr-3">{what}</td>
                  <td className="py-1.5">{where}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          All of these services are outside Zambia, so your data is processed and stored abroad. Sections 70 and 71 of the
          Data Protection Act 2021 restrict processing personal data outside Zambia. Until Levy can offer processing in
          Zambia or an approved transfer route, law firms should not upload documents that identify their clients.
        </p>
        <p>
          Anthropic does not train its models on Levy&apos;s data and deletes it within 30 days, unless it is flagged
          for misuse. OpenAI does not train on API data and keeps abuse-monitoring logs for up to 30 days.
        </p>
      </Section>

      <Section title="How long we keep it">
        <ul className="list-disc pl-5 space-y-1.5">
          <li>Chats, documents, matters and templates: until you delete them, or until you ask us to close your account.</li>
          <li>Records of guest questions: kept without their content, for usage statistics.</li>
          <li>If you ask us to close your account, we delete your account data within 30 days.</li>
        </ul>
      </Section>

      <Section title="Your rights">
        <p>
          Under the Data Protection Act 2021 you can ask what we hold about you, ask us to correct or delete it, object to
          marketing, and withdraw any consent you gave. Email {EMAIL} to do any of these. You can also
          complain to the Office of the Data Protection Commissioner.
        </p>
      </Section>

      <Section title="If we emailed your firm">
        <p>
          We write only to addresses a firm or advocate publishes for business contact. We record where and when we found
          the address, and we send one email unless you reply. If you reply STOP, we remove your address from our list and
          keep only a note of the address so we never write again.
        </p>
      </Section>

      <Section title="Security">
        <p>
          Data is encrypted in transit and at rest in our database, and access is limited to the people who run Levy. If a
          breach affects your data, we will tell you and the Data Protection Commissioner as the law requires.
        </p>
      </Section>

      <Section title="Legal information, not legal advice">
        <p>Levy gives legal information, not legal advice. Check every authority before you rely on it.</p>
      </Section>

      <Section title="Changes">
        <p>If we change this policy, we will update the date above and, for significant changes, tell account holders by email.</p>
      </Section>
    </div>
  )
}
