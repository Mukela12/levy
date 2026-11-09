import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

// The website and the iOS/Android app link to a saved chat differently: the
// app is a static export with no /chat/<id> route (see src/lib/routes.ts).
function load(target) {
  const source = fs.readFileSync(new URL('../src/lib/routes.ts', import.meta.url), 'utf8')
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const exported = {}
  vm.runInNewContext(output, { exports: exported, process: { env: { NEXT_PUBLIC_LEVY_TARGET: target } }, URLSearchParams, encodeURIComponent })
  return exported
}

test('the website keeps its /chat/<id> and /matters/<id> routes', () => {
  const r = load(undefined)
  assert.equal(r.chatPath('abc'), '/chat/abc')
  assert.equal(r.matterPath('m1'), '/matters/m1')
  assert.equal(r.activeChatId('/chat/abc', ''), 'abc')
  assert.equal(r.activeChatId('/chat', ''), null)
  assert.equal(r.activeChatId('/documents', '?id=abc'), null)
})

test('the app carries the id in the query string on one prebuilt page', () => {
  const r = load('app')
  assert.equal(r.chatPath('abc'), '/chat/view/?id=abc')
  assert.equal(r.matterPath('m 1'), '/matters/view/?id=m%201')
  assert.equal(r.activeChatId('/chat/view/', '?id=abc'), 'abc')
  assert.equal(r.activeChatId('/chat/view', 'id=abc'), 'abc')
  assert.equal(r.activeChatId('/chat/', '?id=abc'), null)
})

test('no component builds a /chat/ or /matters/ link by hand', () => {
  const offenders = []
  const walk = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = `${dir}/${e.name}`
      if (e.isDirectory()) walk(p)
      else if (/\.tsx?$/.test(e.name) && !p.endsWith('lib/routes.ts') && /\/(chat|matters)\/\$\{/.test(fs.readFileSync(p, 'utf8'))) offenders.push(p)
    }
  }
  walk(new URL('../src', import.meta.url).pathname)
  assert.deepEqual(offenders, [])
})
