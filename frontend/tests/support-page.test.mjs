import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

// /support is the support URL for both store listings, and its
// #delete-account section is the account-deletion link Google Play asks for.
// Play checks that the page names the app, gives the steps, and says what is
// deleted and what is kept.
const read = (p) => fs.readFileSync(new URL(`../src/${p}`, import.meta.url), 'utf8')

test('the support page carries what Google Play checks on a deletion link', () => {
  const page = read('app/support/page.web.tsx')
  assert.match(page, /id="delete-account"/)
  assert.match(page, /Delete your Levy account/)
  assert.match(page, /Delete my account/)
  assert.match(page, /What is deleted:/)
  assert.match(page, /What is kept:/)
  assert.match(page, /SUPPORT_EMAIL/)
  assert.doesNotMatch(page, /\u2014/, 'no em dashes in Levy wording')
})

test('the support page is website-only, in the sitemap, and opened from the app', () => {
  assert.ok(fs.existsSync(new URL('../src/app/support/page.web.tsx', import.meta.url)))
  assert.ok(!fs.existsSync(new URL('../src/app/support/page.tsx', import.meta.url)))
  assert.match(read('app/sitemap.ts'), /\/support`/)
  assert.match(read('components/account/app-about.tsx'), /\/support`\)/)
})

test('one source for the contact details', () => {
  for (const p of ['app/privacy/page.web.tsx', 'app/support/page.web.tsx'])
    assert.match(read(p), /from '@\/lib\/contact'/, p)
  assert.doesNotMatch(read('app/privacy/page.web.tsx'), /const EMAIL = 'mukelakatungu/)
})
