// The tour and a first visit (src/lib/tour-gate.ts).
// A visitor who has not signed in must reach the message box with nothing in
// the way. On 20 and 21 November 2026 four ads sent 256 people to Levy, the
// tour opened over the page for every one of them, and 3 asked a question.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), 'utf8')
const out = ts.transpileModule(read('../src/lib/tour-gate.ts'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText
const exported = {}
vm.runInNewContext(out, { exports: exported })
const { tourOpensUnasked } = exported

const visit = (over = {}) => ({ signedIn: true, seenOnAccount: false, seenInBrowser: false, onChat: true, awaitingConsent: false, ...over })

test('a visitor who has not signed in never gets the tour unasked', () => {
  for (const seenInBrowser of [false, true]) {
    for (const onChat of [false, true]) {
      assert.equal(tourOpensUnasked(visit({ signedIn: false, seenInBrowser, onChat })), false)
    }
  }
})

test('a new account gets it once, on the chat screen', () => {
  assert.equal(tourOpensUnasked(visit()), true)
  assert.equal(tourOpensUnasked(visit({ onChat: false })), false)
  assert.equal(tourOpensUnasked(visit({ seenOnAccount: true })), false)
  assert.equal(tourOpensUnasked(visit({ seenInBrowser: true })), false)
})

test('in the app the consent screen comes first', () => {
  assert.equal(tourOpensUnasked(visit({ awaitingConsent: true })), false)
})

test('the tour asks the gate, and opens nowhere else except a replay', () => {
  const tour = read('../src/components/onboarding/onboarding-tour.tsx')
  assert.match(tour, /const opens = tourOpensUnasked\(\{/)
  assert.match(tour, /signedIn: Boolean\(user\)/)
  const opensAt = [...tour.matchAll(/setOpen\(true\)/g)].length
  assert.equal(opensAt, 2, 'one for a replay (forceOpen), one behind the gate')
  assert.ok(!/Anonymous: localStorage is all we have/.test(tour))
})
