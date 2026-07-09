import { redirect } from 'next/navigation'

// The bare domain points at the public, indexable Acts directory rather than
// the chat app: it gives the homepage real content for SEO (the brand-domain
// listing), and visitors land on something usable with prominent "Ask Levy"
// CTAs instead of a sign-in-walled chat. Signed-in users reach chat in one tap.
export default function Home() {
  redirect('/acts')
}
