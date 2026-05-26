import type { Metadata, Viewport } from 'next'
import { Inter } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import { SpeedInsights } from '@vercel/speed-insights/next'
import './globals.css'
import { AuthProvider } from '@/components/auth/auth-provider'
import { TooltipProvider } from '@/components/ui/tooltip'

const inter = Inter({ subsets: ['latin'], variable: '--font-sans' })

export const metadata: Metadata = {
  title: 'Levy - AI Legal Assistant for Zambia',
  description: 'Ask questions about Zambian law and get answers grounded in actual legislation with citations.',
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
