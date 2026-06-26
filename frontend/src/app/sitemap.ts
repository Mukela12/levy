import type { MetadataRoute } from 'next'
import { listActs, SITE_URL } from '@/lib/server/corpus'
import { answers } from '@/lib/server/answers'

export const revalidate = 86400

// Public, indexable surface. Per-user routes (saved chats, documents, templates,
// profile) stay private and out of the index — see robots.ts. The bulk of the
// indexable content is the programmatic Acts directory + the answers pages.
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // NOTE: /chat is intentionally excluded — it is the live (billed) chat app,
  // not indexable content. See robots.ts.
  const entries: MetadataRoute.Sitemap = [
    { url: `${SITE_URL}/answers`, changeFrequency: 'weekly', priority: 0.9 },
    { url: `${SITE_URL}/acts`, changeFrequency: 'weekly', priority: 0.9 },
    { url: `${SITE_URL}/study`, changeFrequency: 'monthly', priority: 0.7 },
    { url: `${SITE_URL}/auth/signup`, changeFrequency: 'monthly', priority: 0.4 },
  ]
  for (const a of answers) {
    entries.push({ url: `${SITE_URL}/answers/${a.slug}`, changeFrequency: 'monthly', priority: 0.7 })
  }
  try {
    const acts = await listActs()
    for (const a of acts) {
      entries.push({ url: `${SITE_URL}/acts/${a.slug}`, changeFrequency: 'monthly', priority: 0.6 })
    }
  } catch {
    // if the corpus is briefly unreachable, still return the static entries
  }
  return entries
}
