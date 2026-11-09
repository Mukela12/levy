import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import { createRequire } from 'node:module'
const require = createRequire(import.meta.url)

const source = fs.readFileSync(require.resolve('../src/lib/ui-variant.tsx'), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: {
  jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS,
} }).outputText
// ui-variant imports ./routes for the app/website split; the website build is
// the default here, and appExports below is the app build.
const load = (isApp) => {
  const out = {}
  vm.runInNewContext(compiled, { exports: out, require: (m) => (m === './routes' ? { IS_APP: isApp } : require(m)), process })
  return out
}
const exportsObject = load(false)
const appExports = load(true)

function boot(search, stored = {}, blocked = false) {
  const html = { dataset: {}, style: {}, classList: { toggle(name, value) { html[name] = value } } }
  const localStorage = {
    getItem(key) { if (blocked) throw Error('blocked'); return stored[key] ?? null },
    setItem(key, value) { if (blocked) throw Error('blocked'); stored[key] = value },
  }
  vm.runInNewContext(exportsObject.uiBootScript, {
    document: { documentElement: html }, location: { search }, URLSearchParams, localStorage,
  })
  return html
}

test('query override wins over stored legacy choice', () => {
  const html = boot('?ui=canopy', { 'levy-ui': 'legacy', 'levy-theme': 'light' })
  assert.equal(html.dataset.ui, 'canopy')
  assert.equal(html.style.colorScheme, 'light')
  assert.equal(html.dark, false)
})
test('blocked storage does not prevent explicit Canopy preview', () => {
  const html = boot('?ui=canopy', {}, true)
  assert.equal(html.dataset.ui, 'canopy')
  assert.equal(html.dataset.uiTheme, 'dark')
  assert.equal(html.dark, true)
})
test('legacy remains dark with stored light preference', () => {
  const html = boot('?ui=legacy', { 'levy-theme': 'light' })
  assert.equal(html.dataset.ui, 'legacy')
  assert.equal(html.dark, true)
})
test('unrecognized stored variants fall back safely', () => {
  assert.equal(boot('', { 'levy-ui': 'unknown' }).dataset.ui, exportsObject.BUILD_DEFAULT_VARIANT)
})

test('the app follows the phone until a theme is chosen; the website opens dark', () => {
  const run = (script, prefersLight, stored = {}) => {
    const html = { dataset: {}, style: {}, classList: { toggle(name, value) { html[name] = value } } }
    vm.runInNewContext(script, {
      document: { documentElement: html }, location: { search: '' }, URLSearchParams,
      localStorage: { getItem: (k) => stored[k] ?? null, setItem() {} },
      matchMedia: () => ({ matches: prefersLight }),
    })
    return html.dataset.uiTheme
  }
  assert.equal(run(appExports.uiBootScript, true), 'light')
  assert.equal(run(appExports.uiBootScript, false), 'dark')
  assert.equal(run(appExports.uiBootScript, true, { 'levy-theme': 'dark' }), 'dark')
  assert.equal(run(exportsObject.uiBootScript, true), 'dark')
})
