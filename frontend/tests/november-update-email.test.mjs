// November 2026 user update (renderNovemberUpdateEmail in src/lib/email/templates.ts).
// The email is a short list that links to the article at /updates/november-2026.
// A broadcast cannot be recalled, so what it says and where it points are
// pinned here before it goes anywhere.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), 'utf8')
const load = (path) => {
  const out = ts.transpileModule(read(path), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText
  const exported = {}
  vm.runInNewContext(out, { exports: exported, process: { env: {} }, URL, encodeURIComponent })
  return exported
}
const { renderNovemberUpdateEmail } = load('../src/lib/email/templates.ts')
const { getUpdate } = load('../src/lib/updates.ts')

const PAGE = 'https://www.levylegal.ai/updates/november-2026'

test('the subject names what changed, and a preview says it is one', () => {
  const subject = 'Documents set like court papers, ZambiaLII case checks, final pay'
  assert.equal(renderNovemberUpdateEmail().subject, subject)
  assert.equal(renderNovemberUpdateEmail({ preview: true }).subject, `Preview | ${subject}`)
  assert.match(renderNovemberUpdateEmail({ preview: true }).html, /Preview of a Levy update\./)
})

test('every line of the list opens its own section of the article', () => {
  const e = renderNovemberUpdateEmail()
  const article = getUpdate('november-2026')
  const sections = new Map(article.sections.map((s) => [s.id, s.title]))
  const links = [...e.html.matchAll(/<a href="https:\/\/www\.levylegal\.ai\/updates\/november-2026#([a-z-]+)"[^>]*>([^<&][^<]*)<\/a>/g)]
  assert.equal(links.length, 7)
  for (const [, anchor, label] of links) {
    assert.ok(sections.has(anchor), `no section #${anchor} on the page`)
    assert.equal(sections.get(anchor), label.replace(/&#39;/g, "'"), `the email calls #${anchor} something the page does not`)
    assert.ok(e.text.includes(`- ${label}`), `text lacks ${label}`)
  }
})

test('one button, to the full update', () => {
  const e = renderNovemberUpdateEmail()
  assert.match(e.html, new RegExp(`<a href="${PAGE}" style="display:block;background:#275a42;[^"]*">Read the full update</a>`))
  assert.ok(e.text.includes(`Read the full update: ${PAGE}`))
})

test('it is short enough to read at a glance', () => {
  const words = renderNovemberUpdateEmail().text.split(/\s+/).length
  assert.ok(words <= 110, `${words} words`)
})

test('a reader can reply, unsubscribe and find the privacy policy', () => {
  const e = renderNovemberUpdateEmail()
  assert.match(e.html, /Reply to this email\. It comes straight to me\./)
  assert.match(e.html, /href="mailto:[^"]+\?subject=Unsubscribe%20from%20Levy%20updates"[^>]*>Unsubscribe<\/a>/)
  assert.match(e.html, /href="https:\/\/www\.levylegal\.ai\/privacy"[^>]*>Privacy policy<\/a>/)
  assert.match(e.text, /Unsubscribe: reply to this email with "unsubscribe"\./)
  assert.match(e.html, /You are receiving this because you created a Levy account\./)
  for (const part of [e.html, e.text]) assert.match(part, /Levy gives legal information, not legal advice\./)
})

test('no em dashes, and the images are ones Gmail will show', () => {
  const e = renderNovemberUpdateEmail()
  assert.ok(!(e.subject + e.html + e.text).includes('—'), 'an em dash')
  const images = [...e.html.matchAll(/<img src="([^"]+)"/g)].map((m) => m[1])
  assert.deepEqual(images, ['https://www.levylegal.ai/levy-eagle-email.png'])      // a PNG: Gmail strips SVG
  assert.ok(fs.existsSync(new URL('../public/levy-eagle-email.png', import.meta.url)))
})

test('the send route knows the edition and sends it unless told otherwise', () => {
  const route = read('../src/app/api/email/product-update/route.web.ts')
  assert.match(route, /'november-2026': renderNovemberUpdateEmail,/)
  assert.match(route, /const LATEST_EDITION: keyof typeof EDITIONS = 'november-2026'/)
  assert.match(route, /'october-2026': renderOctoberUpdateEmail,/)      // earlier editions can still be re-rendered
})
