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
