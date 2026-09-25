import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import vm from 'node:vm'

const src = readFileSync(new URL('../src/lib/stream-recovery.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText
const sandbox = { exports: {}, module: { exports: {} } }
vm.createContext(sandbox)
vm.runInContext(js, sandbox)
const { shouldWaitForAnswer } = sandbox.exports

test('a dropped stream waits: the run is still writing the answer', () => {
  assert.equal(shouldWaitForAnswer({ accepted: true, alreadyAnswering: false, signedIn: true }), true)
})

test('a refused duplicate waits for the run that is already going', () => {
  assert.equal(shouldWaitForAnswer({ accepted: false, alreadyAnswering: true, signedIn: true }), true)
})

test('a refusal before the run started reports straight away', () => {
  // Trial used up, rate limited, signed out: nothing is being written, so
  // locking the composer for three minutes would strand the reader.
  assert.equal(shouldWaitForAnswer({ accepted: false, alreadyAnswering: false, signedIn: true }), false)
})

test('a guest never waits, because it cannot read the thread back', () => {
  assert.equal(shouldWaitForAnswer({ accepted: true, alreadyAnswering: false, signedIn: false }), false)
  assert.equal(shouldWaitForAnswer({ accepted: false, alreadyAnswering: true, signedIn: false }), false)
})
