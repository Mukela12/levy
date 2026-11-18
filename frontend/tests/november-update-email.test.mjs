// November 2026 user update (renderNovemberUpdateEmail in src/lib/email/templates.ts).
// A broadcast cannot be recalled, so what it says and how it is addressed are
// pinned here before it goes anywhere.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), 'utf8')
const output = ts.transpileModule(read('../src/lib/email/templates.ts'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText
const exported = {}
vm.runInNewContext(output, { exports: exported, process: { env: {} }, URL, encodeURIComponent })
const { renderNovemberUpdateEmail } = exported

const HEADINGS = [
  'Documents laid out properly.',
  'Levy finishes the document.',
  'Citations traced to what Levy read.',
  'Cases checked against ZambiaLII.',
  'Final pay and gratuity.',
  'Photograph a document.',
  '500 more judgments.',
  'Two smaller things.',
]

test('the send and the preview carry their own subjects', () => {
  const title = "Levy's November update: documents laid out like Zambian court papers"
  assert.equal(renderNovemberUpdateEmail().subject, title)
  assert.equal(renderNovemberUpdateEmail({ preview: true }).subject, `Preview | ${title}`)
  assert.match(renderNovemberUpdateEmail({ preview: true }).html, /Preview of Levy&rsquo;s November update\./)
})

test('every update is in the HTML and in the plain text', () => {
  const e = renderNovemberUpdateEmail()
  for (const heading of HEADINGS) {
    assert.ok(e.html.includes(`<strong>${heading}</strong>`), `html lacks ${heading}`)
    assert.ok(e.text.includes(`- ${heading} `), `text lacks ${heading}`)
  }
  assert.equal((e.html.match(/<strong>/g) || []).length, HEADINGS.length)
})

test('the library figures are the ones measured on 18 November 2026', () => {
  const e = renderNovemberUpdateEmail()
  for (const part of [e.html, e.text]) {
    assert.match(part, /from 1,165 judgments to 1,665/)
  }
  assert.equal(1665 - 1165, 500)
})

test('it says a draft is still a draft, and that Levy is not legal advice', () => {
  const e = renderNovemberUpdateEmail()
  for (const part of [e.html, e.text]) {
    assert.match(part, /have a lawyer look at anything you will file or sign/)
    assert.match(part, /Levy gives legal information, not legal advice\./)
  }
})

test('a reader can unsubscribe and find the privacy policy', () => {
  const e = renderNovemberUpdateEmail()
  assert.match(e.html, /href="mailto:[^"]+\?subject=Unsubscribe%20from%20Levy%20updates"[^>]*>Unsubscribe<\/a>/)
  assert.match(e.html, /href="https:\/\/levylegal\.ai\/privacy"[^>]*>Privacy policy<\/a>/)
  assert.match(e.text, /Unsubscribe: reply to this email with "unsubscribe"\./)
  assert.match(e.html, /You are receiving this because you created a Levy account\./)
})

test('the ZambiaLII check is named, credited, and described as the trial it is', () => {
  const e = renderNovemberUpdateEmail()
  for (const part of [e.html.replace(/&#39;/g, "'"), e.text]) {
    assert.match(part, /looked up in ZambiaLII's index, through Laws\.Africa\./)
    assert.match(part, /This is a trial and the index gives a summary, not the full judgment/)
    assert.match(part, /open the judgment before you rely on it/)
  }
})

test('it stays short', () => {
  const words = renderNovemberUpdateEmail().text.split(/\s+/).length
  assert.ok(words <= 450, `${words} words`)      // 425 when sent; the first draft ran to 610
})

test('no em dashes, and nothing announced that is not there to use yet', () => {
  const e = renderNovemberUpdateEmail()
  const all = e.subject + e.html + e.text
  assert.ok(!all.includes('—'), 'an em dash')
  assert.ok(!/App Store|Google Play|TestFlight/i.test(all))      // the apps are not in the stores
})

test('the send route knows the edition and sends it unless told otherwise', () => {
  const route = read('../src/app/api/email/product-update/route.web.ts')
  assert.match(route, /'november-2026': renderNovemberUpdateEmail,/)
  assert.match(route, /const LATEST_EDITION: keyof typeof EDITIONS = 'november-2026'/)
  assert.match(route, /'october-2026': renderOctoberUpdateEmail,/)      // earlier editions can still be re-rendered
})
