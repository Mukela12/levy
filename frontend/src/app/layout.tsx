import type { Metadata, Viewport } from 'next'
import { Inter } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import { SpeedInsights } from '@vercel/speed-insights/next'
import './globals.css'
import { AuthProvider } from '@/components/auth/auth-provider'
import { TooltipProvider } from '@/components/ui/tooltip'

const inter = Inter({ subsets: ['latin'], variable: '--font-sans' })

// Canonical site URL. Crawlers that hit the Vercel alias still see canonical
// tags pointing here, so SEO authority consolidates on the official domain
// while the alias keeps working for existing users.
const SITE_URL = 'https://levylegal.ai'
const TITLE = 'Levy: AI Legal Assistant for Zambian Law'
// Shown as the search-result snippet under the link. ~155 chars, keyword-rich,
// and written to earn the click: what it is, that it is free, what you can do.
const DESCRIPTION =
  'Ask any question about Zambian law and get clear answers grounded in the Acts and case law, with citations. Free legal research, document drafting and exam prep.'

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: TITLE,
    template: '%s | Levy',
  },
  description: DESCRIPTION,
  applicationName: 'Levy',
  keywords: [
    'Zambian law',
    'Zambia legal AI',
    'Zambian legislation',
    'Zambian Acts of Parliament',
    'legal assistant Zambia',
    'Zambian Constitution',
    'Zambian legal research',
    'Laws of Zambia',
    'Zambia case law',
  ],
  authors: [{ name: 'Levy' }],
  creator: 'Levy',
  alternates: { canonical: '/' },
  openGraph: {
    type: 'website',
    siteName: 'Levy',
    title: TITLE,
    description: DESCRIPTION,
    url: SITE_URL,
    locale: 'en_ZM',
  },
  twitter: {
    card: 'summary_large_image',
    title: TITLE,
    description: DESCRIPTION,
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true },
  },
}

// viewportFit:'cover' makes env(safe-area-inset-*) resolve to real values on
// notched iPhones so the top bar can clear the status bar. Pinch-zoom stays
// enabled (no maximumScale/userScalable) for accessibility.
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: '#0a0a0b',
  colorScheme: 'dark',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} h-full dark`}>
      <body className="min-h-full bg-background text-foreground antialiased">
        <AuthProvider>
          <TooltipProvider>{children}</TooltipProvider>
        </AuthProvider>
        <Analytics />
        <SpeedInsights />
      </body>
    </html>
  )
}
