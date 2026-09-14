import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, existsSync } from 'node:fs'

const read = path => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('Canopy authentication retains real auth and confirmation-dependent signup', () => {
  const source = read('components/canopy/auth-screen.tsx')
  assert.match(source, /await signIn\(email.trim\(\), password\)/)
  assert.match(source, /if \(result.session\?\.access_token\)/)
  assert.match(source, /Check your email to confirm your account/)
  assert.match(source, /finally \{ setBusy\(false\) \}/)
  assert.match(source, /resetPasswordForEmail/)
})

test('Password recovery has a route and checks a session before updating', () => {
  assert.ok(existsSync(new URL('../src/app/auth/reset-password/page.tsx', import.meta.url)))
  const source = read('components/canopy/auth-screen.tsx')
  assert.ok(source.indexOf('if (!data.session)') < source.indexOf('updateUser({ password })'))
  assert.match(source, /autoComplete=\{signup \|\| reset \? 'new-password' : 'current-password'\}/)
})

test('Matter persistence rejects errors and zero-row updates', () => {
  const source = read('lib/matters.ts').split('export async function updateMatter')[1].split('export async function deleteMatter')[0]
  assert.match(source, /if \(error\) throw error/)
  assert.match(source, /if \(!data\) throw new Error/)
  assert.match(read('app/(dashboard)/matters/[id]/page.tsx'), /if \(await persist\(\{ parties: next \}\)\)/)
})
