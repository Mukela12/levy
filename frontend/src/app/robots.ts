import type { MetadataRoute } from 'next'

const SITE_URL = 'https://levylegal.ai'

// Index the public content (Acts, answers, study); keep the app + private,
// per-user routes OUT of the index. IMPORTANT: /chat is disallowed entirely.
// It is the live chat app, not content, and crawling /chat?q=... links would
// otherwise hammer the (billed) LLM endpoint. The composer only pre-fills from
// ?q= now (no auto-send), but we also keep crawlers off /chat as defense.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      disallow: [
        '/chat',       // the live chat app (and all /chat?q=... and saved sessions)
        '/documents',
        '/templates',
        '/profile',
        '/search',
        '/api/',
      ],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  }
}
