import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

// A dropped connection must read as one (src/lib/network.ts): "Sorry, I
// encountered an error" sent people looking for a fault that was lost signal.
function load(onLine) {
  const src = fs.readFileSync(new URL('../src/lib/network.ts', import.meta.url), 'utf8')
  const js = ts.transpileModule(src, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const exports = {}
  vm.runInNewContext(js, { exports, navigator: { onLine }, TypeError, Error })
  return exports
}

test('offline phones are told they are offline', () => {
  const n = load(false)
  assert.match(n.connectionMessage(new Error('anything')), /^You're offline\./)
})

test('the message only promises the question is back when it is', () => {
  const n = load(false)
  assert.match(n.connectionMessage(new Error('x'), true), /back in the box/)
  assert.doesNotMatch(n.connectionMessage(new Error('x'), false), /back in the box/)
})

test('fetch failures from each engine count as unreachable', () => {
  const n = load(true)
  for (const m of ['Failed to fetch', 'Load failed', 'NetworkError when attempting to fetch resource.', 'Network request failed'])
    assert.match(n.connectionMessage(new TypeError(m)), /couldn't be reached/, m)
})

test('ordinary bugs and server errors are not blamed on the connection', () => {
  const n = load(true)
  assert.equal(n.connectionMessage(new TypeError("Cannot read properties of undefined (reading 'id')")), null)
  assert.equal(n.connectionMessage(new Error('API error: 500')), null)
})

test("Supabase's plain error object is read too", () => {
  const n = load(true)
  assert.match(n.connectionMessage({ message: 'TypeError: Failed to fetch', details: '', hint: '', code: '' }), /couldn't be reached/)
  assert.equal(n.connectionMessage({ message: 'new row violates row-level security policy', code: '42501' }), null)
})

test("the app's native status wins over the WebView's flag", () => {
  const n = load(true)              // Android's WebView says online in airplane mode
  n.setNativeConnected(false)
  assert.ok(n.isOffline())
  n.setNativeConnected(true)
  assert.ok(!n.isOffline())
})
