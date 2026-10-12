// Signup source capture (src/lib/attribution.ts): what a page load records.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const output = ts.transpileModule(fs.readFileSync(new URL('../src/lib/attribution.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText
const exported = {}
vm.runInNewContext(output, { exports: exported, URL })
const { readTouch } = exported
const DAY = new Date('2026-10-14T08:00:00Z')

test('UTM tags are kept with the landing page', () => {
  const t = readTouch('https://www.levylegal.ai/chat?utm_source=linkedin&utm_medium=post&utm_campaign=final-pay', '', DAY)
  assert.deepEqual({ ...t }, { utm_source: 'linkedin', utm_medium: 'post', utm_campaign: 'final-pay', landing: '/chat', at: '2026-10-14' })
})

test('another site is kept as its domain only', () => {
  const t = readTouch('https://levylegal.ai/', 'https://www.linkedin.com/feed/update/urn:li:activity:7505423965583032320/', DAY)
  assert.equal(t.ref_host, 'linkedin.com')
  assert.equal(t.landing, '/')
})

test('a direct visit or a move within Levy records nothing', () => {
  assert.equal(readTouch('https://levylegal.ai/chat', '', DAY), null)
  assert.equal(readTouch('https://levylegal.ai/chat', 'https://www.levylegal.ai/answers/x', DAY), null)
})

test('long or broken values are cut, not kept whole', () => {
  const t = readTouch(`https://levylegal.ai/?utm_source=${'a'.repeat(300)}`, 'not a url', DAY)
  assert.equal(t.utm_source.length, 100)
  assert.equal(t.ref_host, undefined)
})
