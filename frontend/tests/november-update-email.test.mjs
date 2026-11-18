// November 2026 user update (renderNovemberUpdateEmail in src/lib/email/templates.ts).
// The email is a short list and one button that opens /updates/november-2026.
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
const { renderNovemberUpdateEmail, renderNovemberUpdatePlainEmail } = load('../src/lib/email/templates.ts')
const { getUpdate } = load('../src/lib/updates.ts')

const PAGE = 'https://www.levylegal.ai/updates/november-2026'
const SUBJECT = 'Documents set like court papers, ZambiaLII case checks, final pay'
const links = (html) => [...html.matchAll(/<a href="([^"]+)"/g)].map((m) => m[1])
const lines = (text) => text.split('\n').filter((l) => l.startsWith('- ')).map((l) => l.slice(2))

test('the subject names what changed, and a preview says which form it is', () => {
  assert.equal(renderNovemberUpdateEmail().subject, SUBJECT)
  assert.equal(renderNovemberUpdatePlainEmail().subject, SUBJECT)
  // two previews must not thread together in Gmail, or their tabs cannot be told apart
  assert.equal(renderNovemberUpdateEmail({ preview: true }).subject, `Preview (list) | ${SUBJECT}`)
  assert.equal(renderNovemberUpdatePlainEmail({ preview: true }).subject, `Preview (plain) | ${SUBJECT}`)
  assert.match(renderNovemberUpdateEmail({ preview: true }).html, /Preview of a Levy update\./)
})

test('every line of the list is a section of the article, under the same name', () => {
  const titles = new Set(getUpdate('november-2026').sections.map((s) => s.title))
  for (const e of [renderNovemberUpdateEmail(), renderNovemberUpdatePlainEmail()]) {
    const listed = lines(e.text)
    assert.equal(listed.length, 7)
    for (const label of listed) {
      assert.ok(titles.has(label), `the page has no section called "${label}"`)
      assert.ok(e.html.includes(`>${label.replace(/'/g, '&#39;')}<`), `html lacks ${label}`)
    }
  }
})

test('the list is plain text and there is one way in: Gmail filed a link on every line under Promotions', () => {
  const e = renderNovemberUpdateEmail()
  assert.deepEqual(links(e.html).map((h) => h.replace(/^mailto:[^?]+/, 'mailto:')), [
    PAGE,
    'mailto:?subject=Unsubscribe%20from%20Levy%20updates',
    'https://www.levylegal.ai/privacy',
  ])
  assert.ok(!e.html.includes('#court-documents'))
  assert.match(e.html, new RegExp(`<a href="${PAGE}" style="display:block;background:#275a42;[^"]*">Read the full update</a>`))
  assert.ok(e.text.includes(`Read the full update: ${PAGE}`))
})

test('the plain form is a note with no picture and no button', () => {
  const e = renderNovemberUpdatePlainEmail()
  assert.ok(!e.html.includes('<img'))
  assert.ok(!e.html.includes('background:#275a42'))
  assert.equal(links(e.html).length, 3)
  assert.ok(e.html.includes(`<a href="${PAGE}" style="color:#275a42;">www.levylegal.ai/updates/november-2026</a>`))
  assert.match(e.html, /<p[^>]*>Hi,<\/p>/)
  assert.equal(e.text, renderNovemberUpdateEmail().text)      // one plain-text part for both
})

test('it is short enough to read at a glance', () => {
  const words = renderNovemberUpdateEmail().text.split(/\s+/).length
  assert.ok(words <= 110, `${words} words`)
})

test('a reader can reply, unsubscribe and find the privacy policy', () => {
  for (const e of [renderNovemberUpdateEmail(), renderNovemberUpdatePlainEmail()]) {
    assert.match(e.html, /Reply to this email\. It comes straight to me\./)
    assert.match(e.html, /href="mailto:[^"]+\?subject=Unsubscribe%20from%20Levy%20updates"[^>]*>Unsubscribe<\/a>/)
    assert.match(e.html, /href="https:\/\/www\.levylegal\.ai\/privacy"[^>]*>Privacy policy<\/a>/)
    assert.match(e.text, /Unsubscribe: reply to this email with "unsubscribe"\./)
    assert.match(e.html, /You are receiving this because you created a Levy account\./)
    for (const part of [e.html, e.text]) assert.match(part, /Levy gives legal information, not legal advice\./)
  }
})

test('no em dashes, and the one picture is a kind Gmail will show', () => {
  const e = renderNovemberUpdateEmail()
  assert.ok(!(e.subject + e.html + e.text + renderNovemberUpdatePlainEmail().html).includes('—'), 'an em dash')
  const images = [...e.html.matchAll(/<img src="([^"]+)"/g)].map((m) => m[1])
  assert.deepEqual(images, ['https://www.levylegal.ai/levy-eagle-email.png'])      // a PNG: Gmail strips SVG
  assert.ok(fs.existsSync(new URL('../public/levy-eagle-email.png', import.meta.url)))
})

test('the send route knows both forms and sends the designed one unless told otherwise', () => {
  const route = read('../src/app/api/email/product-update/route.web.ts')
  assert.match(route, /'november-2026': renderNovemberUpdateEmail,/)
  assert.match(route, /'november-2026-plain': renderNovemberUpdatePlainEmail,/)
  assert.match(route, /const LATEST_EDITION: keyof typeof EDITIONS = 'november-2026'/)
  assert.match(route, /'october-2026': renderOctoberUpdateEmail,/)      // earlier editions can still be re-rendered
})
