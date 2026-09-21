import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

// Only the host decision is tested here; the redirect itself is NextResponse's.
const source = fs.readFileSync(new URL('../src/proxy.ts', import.meta.url), 'utf8')
  .replace(/import[^\n]*from 'next\/server'\n/g, '')
  .replace(/import type[^\n]*\n/g, '')
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
const exported = {}
vm.runInNewContext(output, { exports: exported, process: { env: {} }, Boolean, String })
const { sendToCanonical, CANONICAL } = exported

test('a production hit on the vercel.app alias goes to the real domain', () => {
  assert.equal(sendToCanonical('levy-ten.vercel.app', 'production'), true)
})
test('the canonical domain is left alone', () => {
  assert.equal(sendToCanonical(CANONICAL, 'production'), false)
})
test('preview deployments answer on their own host', () => {
  assert.equal(sendToCanonical('levy-git-branch-x.vercel.app', 'preview'), false)
  assert.equal(sendToCanonical('levy-ten.vercel.app', undefined), false)
})
test('a custom domain is never redirected', () => {
  assert.equal(sendToCanonical('levylegal.ai', 'production'), false)
  assert.equal(sendToCanonical('', 'production'), false)
})
