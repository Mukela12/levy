import type { Metadata } from 'next'
import Image from 'next/image'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import { getUpdate, longDate, updates } from '@/lib/updates'

const SITE_URL = 'https://www.levylegal.ai'

export const dynamicParams = false

export function generateStaticParams() {
  return updates.map((u) => ({ slug: u.slug }))
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params
  const u = getUpdate(slug)
  if (!u) return { title: 'Update not found' }
  const url = `${SITE_URL}/updates/${u.slug}`
  const image = u.sections.find((s) => s.image)?.image
  return {
    title: `${u.month}: ${u.title}`,
    description: u.summary,
    alternates: { canonical: url },
    openGraph: {
      type: 'article',
      title: u.title,
      description: u.summary,
      url,
      publishedTime: u.date,
      ...(image ? { images: [{ url: image.src, width: image.width, height: image.height, alt: image.alt }] } : {}),
    },
  }
}

export default async function UpdatePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const u = getUpdate(slug)
  if (!u) notFound()

  const at = updates.indexOf(u)
  const newer = at > 0 ? updates[at - 1] : null
  const older = at < updates.length - 1 ? updates[at + 1] : null
  const firstImage = u.sections.find((s) => s.image)?.id

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'BlogPosting',
    headline: u.title,
    description: u.summary,
    datePublished: u.date,
    url: `${SITE_URL}/updates/${u.slug}`,
    author: { '@type': 'Person', name: 'Mukela Katungu' },
    publisher: { '@type': 'Organization', name: 'Levy' },
  }

  return (
    <article>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />

      <div className="lu-back">
        <Link href="/updates" className="lu-back-link">
          All updates
        </Link>
      </div>

      <header className="lu-head">
        <span className="lu-month">{u.month}</span>
        <h1 className="lu-title">{u.title}</h1>
        <p className="lu-date">
          Published <time dateTime={u.date}>{longDate(u.date)}</time>
        </p>
      </header>

      <p className="lu-intro">{u.intro}</p>

      <ol className="lu-contents" aria-label="In this update">
        {u.sections.map((s) => (
          <li key={s.id}>
            <a href={`#${s.id}`}>{s.title}</a>
          </li>
        ))}
        {u.smaller?.length ? (
          <li>
            <a href="#smaller-improvements">Smaller improvements</a>
          </li>
        ) : null}
      </ol>

      {u.sections.map((s) => (
        <section key={s.id} id={s.id} className="lu-section">
          <h2>{s.title}</h2>

          {s.image && (
            <figure className="lu-figure">
              <Image
                src={s.image.src}
                alt={s.image.alt}
                width={s.image.width}
                height={s.image.height}
                sizes="(max-width: 728px) 100vw, 680px"
                priority={s.id === firstImage}
              />
              <figcaption>{s.image.caption}</figcaption>
            </figure>
          )}

          {s.body.map((p, i) => (
            <ReactMarkdown key={i}>{p}</ReactMarkdown>
          ))}

          {s.how?.length ? (
            <div className="lu-how">
              <p className="lu-label">How to use it</p>
              {s.how.length === 1 ? (
                <ReactMarkdown>{s.how[0]}</ReactMarkdown>
              ) : (
                <ol>
                  {s.how.map((step, i) => (
                    <li key={i}>
                      <ReactMarkdown>{step}</ReactMarkdown>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          ) : null}

          {s.tryIt && (
            <Link href={`/chat?q=${encodeURIComponent(s.tryIt)}`} className="lu-try">
              <span className="lu-try-text">
                <small>Try it in Levy</small>
                {s.tryIt}
              </span>
              <span className="lu-try-arrow" aria-hidden="true">
                &rarr;
              </span>
            </Link>
          )}

          {s.note && (
            <aside className="lu-note">
              <p>{s.note}</p>
            </aside>
          )}
        </section>
      ))}

      {u.smaller?.length ? (
        <section id="smaller-improvements" className="lu-section">
          <h2>Smaller improvements</h2>
          <ul className="lu-smaller">
            {u.smaller.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <footer className="lu-end">
        <p>
          If something does not work the way this page says, use the thumbs down under the answer or reply to the update
          email. I read every one.
        </p>
        <p>Mukela Katungu, founder of Levy</p>

        <nav className="lu-pager" aria-label="Other updates">
          {older && (
            <Link href={`/updates/${older.slug}`}>
              <small>Earlier</small>
              <span>{older.month}</span>
            </Link>
          )}
          {newer && (
            <Link href={`/updates/${newer.slug}`}>
              <small>Later</small>
              <span>{newer.month}</span>
            </Link>
          )}
        </nav>
      </footer>
    </article>
  )
}
