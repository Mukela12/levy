import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

// The app has no server, so emailed links and the website's route handlers
// must point at the website by full URL, and website-only pages open in the
// in-app browser (src/lib/native.ts).
function load(target) {
  const read = (f) => ts.transpileModule(fs.readFileSync(new URL(`../src/lib/${f}`, import.meta.url), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const env = { NEXT_PUBLIC_LEVY_TARGET: target }
  const routes = {}
  vm.runInNewContext(read('routes.ts'), { exports: routes, process: { env }, URLSearchParams, encodeURIComponent })
  const native = {}
  vm.runInNewContext(read('native.ts'), {
    exports: native, process: { env }, window: { location: { origin: 'https://www.levylegal.ai' } },
    require: (m) => (m === './routes' ? routes : {}),
  })
  return native
}

test('the website keeps its own links', () => {
  const n = load(undefined)
  assert.equal(n.siteRoute('/api/email/welcome'), '/api/email/welcome')
  assert.equal(n.linkTarget('/auth/reset-password'), 'https://www.levylegal.ai/auth/reset-password')
})

test('the app sends emailed links and route calls to the website', () => {
  const n = load('app')
  assert.equal(n.siteRoute('/api/email/welcome'), 'https://www.levylegal.ai/api/email/welcome')
  assert.equal(n.linkTarget('/auth/reset-password'), 'https://www.levylegal.ai/auth/reset-password')
})

test('website-only pages are recognised, the app pages are not', () => {
  const { WEB_ONLY_PATH } = load('app')
  for (const p of ['/acts', '/acts/', '/acts/employment-code-act', '/answers/x', '/privacy', '/support', '/support/', '/api/email/welcome', '/llms.txt'])
    assert.ok(WEB_ONLY_PATH.test(p), p)
  for (const p of ['/chat/', '/chat/view/', '/matters/', '/documents/', '/actsy', '/study/'])
    assert.ok(!WEB_ONLY_PATH.test(p), p)
})
