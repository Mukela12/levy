import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

// The app asks before a question goes to the AI services (App Store 5.1.2(i))
// and stores the answer on the account (src/lib/ai-providers.ts). The privacy
// policy prints the same list, so the two can't name different companies.
function load() {
  const src = fs.readFileSync(new URL('../src/lib/ai-providers.ts', import.meta.url), 'utf8')
  const js = ts.transpileModule(src, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const exports = {}
  vm.runInNewContext(js, { exports })
  return exports
}

test('consent counts only when it covers the current list', () => {
  const { currentAiConsent, AI_CONSENT_VERSION } = load()
  assert.equal(currentAiConsent(undefined), null)
  assert.equal(currentAiConsent({}), null)
  assert.equal(currentAiConsent({ ai_consent: 'yes' }), null)
  assert.equal(currentAiConsent({ ai_consent: { version: AI_CONSENT_VERSION - 1, at: '2026-11-10T00:00:00Z' } }), null)
  const ok = currentAiConsent({ ai_consent: { version: AI_CONSENT_VERSION, at: '2026-11-10T00:00:00Z' } })
  assert.equal(ok.version, AI_CONSENT_VERSION)
})

test('the consent screen names every AI company the backend calls', () => {
  const { AI_PROVIDERS } = load()
  const names = AI_PROVIDERS.map((p) => p.name).join(' | ')
  for (const company of ['Anthropic', 'OpenAI', 'Google', 'Moonshot', 'OpenRouter', 'Tavily'])
    assert.ok(names.includes(company), company)
  for (const p of AI_PROVIDERS) assert.ok(p.what && p.where, p.name)
})

test('the privacy policy prints the same list', () => {
  const page = fs.readFileSync(new URL('../src/app/privacy/page.web.tsx', import.meta.url), 'utf8')
  assert.match(page, /AI_PROVIDERS\.map/)
  assert.doesNotMatch(page, /\['Anthropic',/)
})
