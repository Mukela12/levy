import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const output = ts.transpileModule(fs.readFileSync(new URL('../src/lib/download.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText
const exported = {}
vm.runInNewContext(output, { exports: exported, URL })
const { withDownloadParam, filenameFor, isInAppBrowser, isFresh, LINK_TTL_MS } = exported

const UA = {
  iphoneSafari: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1',
  androidChrome: 'Mozilla/5.0 (Linux; Android 14; SM-A146P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36',
  facebook: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 [FBAN/FBIOS;FBAV/470.0.0.37.108;FBBV/123]',
  instagram: 'Mozilla/5.0 (Linux; Android 13; TECNO KI5k Build/TP1A; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/127.0.0.0 Mobile Safari/537.36 Instagram 345.0.0.34.94 Android',
  linkedin: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 [LinkedInApp]/9.30.1',
  androidWebView: 'Mozilla/5.0 (Linux; Android 12; itel A665L; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.0.0 Mobile Safari/537.36',
}

test('real browsers are not in-app browsers', () => {
  assert.equal(isInAppBrowser(UA.iphoneSafari), false)
  assert.equal(isInAppBrowser(UA.androidChrome), false)
  assert.equal(isInAppBrowser(''), false)
  assert.equal(isInAppBrowser(undefined), false)
})

test('app browsers that often cannot save files are recognised', () => {
  for (const k of ['facebook', 'instagram', 'linkedin', 'androidWebView']) assert.equal(isInAppBrowser(UA[k]), true, k)
})

test('the download parameter makes storage send an attachment', () => {
  const u = withDownloadParam('https://x.supabase.co/storage/v1/object/sign/artifacts/a.pdf?token=abc', 'Letter.pdf')
  assert.match(u, /token=abc/)
  assert.match(u, /download=Letter\.pdf/)
  assert.equal(withDownloadParam('not a url', 'x.pdf'), 'not a url')
})

test('filenames survive every phone', () => {
  assert.equal(filenameFor('Notice of Motion: Banda v ZESCO / 2026', 'pdf'), 'Notice of Motion- Banda v ZESCO - 2026.pdf')
  assert.equal(filenameFor('', 'docx'), 'Levy document.docx')
  assert.equal(filenameFor('a\u0000b', 'pdf'), 'ab.pdf')
  assert.ok(filenameFor('x'.repeat(200), 'pdf').length <= 84)
})

test('a signed link is reused only while it is well inside its hour', () => {
  const now = 1_000_000_000
  assert.equal(isFresh({ url: 'u', at: now - 60_000 }, now), true)
  assert.equal(isFresh({ url: 'u', at: now - LINK_TTL_MS - 1 }, now), false)
  assert.equal(isFresh(undefined, now), false)
  assert.ok(LINK_TTL_MS < 60 * 60 * 1000)
})

test('the card never opens a new tab after an await', () => {
  const src = fs.readFileSync(new URL('../src/components/chat/artifact-card.tsx', import.meta.url), 'utf8')
  // The old path awaited, then clicked a target="_blank" link: popup-blocked on phones, silently.
  assert.ok(!/target\s*=\s*['"]_blank['"]/.test(src), 'no programmatic new tab')
  assert.ok(!src.includes("a.target = '_blank'"))
  assert.match(src, /window\.location\.assign\(withDownloadParam/)
  assert.match(src, /download=\{pdfName\}/)
})
