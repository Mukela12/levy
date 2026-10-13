// Law-firm demo invitation (renderFirmOutreachEmail in src/lib/email/templates.ts).
// The ECT Act 2021 s.64(2) wants the sender's place of business and phone, where
// the address was found, an opt-out and the privacy policy in every marketing email.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const output = ts.transpileModule(fs.readFileSync(new URL('../src/lib/email/templates.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText
const exported = {}
vm.runInNewContext(output, { exports: exported, process: { env: {} }, URL, encodeURIComponent })
const { renderFirmOutreachEmail } = exported

const SENDER = { business: 'Levy (Mukela Katungu)', address: 'Plot 1, Example Road, Lusaka', phone: '+260 970 000000' }
const base = { firm: 'Example & Co', source: "the firm's website (example.co.zm/contact)", sourceDate: '13 October 2026', sender: SENDER }

test('every email carries the identity, source, opt-out, rights and privacy policy', () => {
  const e = renderFirmOutreachEmail(base)
  for (const part of [SENDER.address, SENDER.phone, 'example.co.zm/contact', '13 October 2026', 'reply STOP', 'Data Protection Commissioner', '/privacy']) {
    assert.ok(e.text.includes(part), `text lacks ${part}`)
    assert.ok(e.html.includes(part.replace(/&/g, '&amp;').replace(/'/g, '&#39;')) || e.html.includes(part), `html lacks ${part}`)
  }
  assert.match(e.text, /only email I will send unless you reply/)
})

test('the firm is greeted as a team, never as colleagues', () => {
  const e = renderFirmOutreachEmail(base)
  assert.ok(e.text.startsWith('Dear Example & Co team,'))
  assert.ok(!/colleague/i.test(e.html + e.text))
  assert.match(e.text, /software engineer/)
})

test('the subject follows the practice, and variant b names the firm first', () => {
  assert.equal(renderFirmOutreachEmail({ ...base, practice: 'employment' }).subject, 'Employment Code final-pay checks for Example & Co')
  assert.match(renderFirmOutreachEmail({ ...base, practice: 'litigation' }).subject, /still good law/)
  assert.match(renderFirmOutreachEmail({ ...base, variant: 'b' }).subject, /^Example & Co: /)
})

test('a hook is its own paragraph and is left out when there is none', () => {
  const hook = 'Cases your firm has argued are already in its library.'
  assert.ok(renderFirmOutreachEmail({ ...base, hook }).text.includes(`\n\n${hook}\n\n`))
  assert.ok(!renderFirmOutreachEmail(base).text.includes('your firm has argued'))
})

test('missing sender details show as placeholders, never as blanks', () => {
  const e = renderFirmOutreachEmail({ firm: 'Example & Co' })
  assert.ok(e.text.includes('[street address], Lusaka') && e.text.includes('[phone]') && e.text.includes('[source and date]'))
})

test('no em dashes in Levy wording', () => {
  const e = renderFirmOutreachEmail({ ...base, hook: 'A hook.' })
  assert.ok(!(e.html + e.text + e.subject).includes('—'))
})
