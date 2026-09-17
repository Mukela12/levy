import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const output = ts.transpileModule(fs.readFileSync(new URL('../src/lib/source-model.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText
const exported = {}
vm.runInNewContext(output, { exports: exported, URL })
const { sourceModel, safeSourceUrl } = exported
const passage = { id: 'chunk-1', document_id: 'doc-1', act_name: 'Example Act', page_start: 2 }
const verdict = { kind: 'statute', text: 'Example Act No. 3 of 2019', title: 'Example Act No. 3 of 2019', document_id: 'doc-1', status: 'verified' }
const model = (v = verdict) => sourceModel({ citations: [passage], blocks: [{ kind: 'citation_audit', citations: [v] }] })

test('null persisted arrays are safe and neutral', () => {
  const value = sourceModel({ citations: null, webSources: null, blocks: null })
  assert.equal(value.rows.length, 0)
  assert.equal(value.verified, 0)
  assert.equal(value.state, 'unavailable')
})
test('retrieval alone is not verification', () => {
  assert.equal(sourceModel({ citations: [passage] }).rows[0].verification, 'none')
})
test('matching identity audit earns only a library badge', () => {
  assert.equal(model().verified, 1)
})
test('wrong number, year, foreign status and missing ID withhold positive badge', () => {
  for (const change of [{ title: 'Example Act No. 4 of 2019' }, { title: 'Example Act No. 3 of 2020' }, { foreign: true }, { document_id: undefined }]) {
    assert.equal(model({ ...verdict, ...change }).verified, 0)
  }
})
test('same-page distinct passages remain selectable', () => {
  const value = sourceModel({ citations: [passage, { ...passage, id: 'chunk-2' }, passage] })
  assert.equal(value.rows.length, 1)
  assert.equal(value.rows[0].passages.length, 2)
})
test('same-title different documents are not merged', () => {
  assert.equal(sourceModel({ citations: [passage, { ...passage, document_id: 'doc-2' }] }).rows.length, 2)
})
test('links reject executable schemes and embedded credentials', () => {
  for (const value of ['javascript:alert(1)', 'data:text/html,test', 'https://user:password@example.com']) assert.equal(safeSourceUrl(value), null)
  assert.equal(safeSourceUrl('https://example.com/document.pdf'), 'https://example.com/document.pdf')
})
test('a repealed Act is never verified and names its replacement', () => {
  const value = model({ ...verdict, law_status: 'repealed', replaced_by: ['Children’s Code Act, 2022'] })
  assert.equal(value.verified, 0)
  assert.equal(value.review, 1)
  assert.equal(value.rows[0].lawStatus, 'repealed')
  assert.deepEqual([...value.rows[0].replacedBy], ['Children’s Code Act, 2022'])  // copied out of the vm realm
})
test('a passed but not started repeal keeps the badge and carries a note', () => {
  const value = model({ ...verdict, law_status: 'repeal pending', replaced_by: ['National Pension Scheme Act, 2026'] })
  assert.equal(value.verified, 1)
  assert.equal(value.rows[0].lawStatus, 'repeal pending')
})
test('a repeal note in the matched title is not a year conflict', () => {
  const v = { kind: 'statute', text: 'Roads and Road Traffic Act, 1995', title: 'Roads and Road Traffic Act [repealed by the Road Traffic Act, 2002]', document_id: 'doc-1', status: 'verified' }
  assert.equal(model(v).rows[0].conflict, false)
})
test('a not-found verdict never carries a law status', () => {
  const value = model({ ...verdict, status: 'not_found', document_id: undefined, law_status: 'repealed' })
  assert.ok(value.rows.every((r) => r.lawStatus === undefined))
})
test('a repeal the answer already names is noted, not queued for review', () => {
  const value = model({ ...verdict, law_status: 'repealed', replaced_by: ['Employment Code Act, 2019'], acknowledged: true })
  assert.equal(value.rows[0].verification, 'noted')
  assert.equal(value.review, 0)
  assert.equal(value.verified, 0)
  assert.equal(value.noted, 1)
})
test('an acknowledged repeal with a number conflict still needs review', () => {
  const value = model({ ...verdict, title: 'Example Act No. 4 of 2019', law_status: 'repealed', acknowledged: true })
  assert.equal(value.rows[0].verification, 'review')
})
