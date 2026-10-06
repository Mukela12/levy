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
test('unverified commencement keeps only the library identity badge and carries a note', () => {
  const value = model({ ...verdict, law_status: 'repeal pending', replaced_by: ['National Pension Scheme Act, 2026'] })
  assert.equal(value.verified, 1)
  assert.equal(value.rows[0].lawStatus, 'repeal pending')
})
test('citation explanations never infer current force from missing commencement evidence', () => {
  const source = fs.readFileSync(new URL('../src/components/canopy/answer-sources.tsx', import.meta.url), 'utf8')
  assert.match(source, /Commencement unverified/)
  assert.match(source, /not proof that this Act remains in force/)
  assert.doesNotMatch(source, /Still in force|The Act is still law|This Act is still law|In force until|In force, replacement passed/)
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

// A live Act can carry a dead section: section 24 of the Immigration and
// Deportation Act 2010, repealed in 2016 while the Act stayed in force.
const deadSection = { section: '24', status: 'repealed', by: 'Immigration and Deportation (Amendment) Act, 2016 (No. 19 of 2016)' }
test('an answer relying on a repealed section is not verified', () => {
  const value = model({ ...verdict, section_status: [{ ...deadSection, acknowledged: false }] })
  assert.equal(value.verified, 0)
  assert.equal(value.review, 1)
  assert.equal(value.rows[0].deadSections.length, 1)
  assert.equal(value.rows[0].deadSections[0].section, '24')
})
test('an answer that says the section was repealed keeps its badge', () => {
  const value = model({ ...verdict, section_status: [{ ...deadSection, acknowledged: true }] })
  assert.equal(value.verified, 1)
  assert.equal(value.rows[0].deadSections[0].acknowledged, true)
})
test('one unqualified mention of a dead section is enough to need review', () => {
  // The same Act cited two ways lands on one row; one of them is unqualified.
  const v1 = { ...verdict, text: 'Example Act, 2019', section_status: [{ ...deadSection, acknowledged: true }] }
  const v2 = { ...verdict, section_status: [{ ...deadSection, acknowledged: false }] }
  const value = sourceModel({ citations: [passage], blocks: [{ kind: 'citation_audit', citations: [v1, v2] }] })
  assert.equal(value.rows[0].deadSections.length, 1)
  assert.equal(value.rows[0].deadSections[0].acknowledged, false)
  assert.equal(value.rows[0].verification, 'review')
})
test('a not-found citation never carries a dead section', () => {
  const value = model({ ...verdict, status: 'not_found', section_status: [deadSection] })
  assert.equal(value.rows[0].deadSections.length, 0)
})

// The module runs in its own VM realm; compare plain copies.
const plain = (x) => JSON.parse(JSON.stringify(x))
test('an Act cited as law but not in force needs review; said so, it is noted', () => {
  const v = { ...verdict, law_status: 'not in force', still_applies: ['Old Act, 2010'] }
  const row = model(v).rows[0]
  assert.equal(row.lawStatus, 'not in force')
  assert.equal(row.verification, 'review')
  assert.deepEqual(plain(row.stillApplies), ['Old Act, 2010'])
  assert.equal(model({ ...v, acknowledged: true }).rows[0].verification, 'noted')
})
test('retrieved passages carry their own labels when nothing was cited', () => {
  const p = (id, section, extra) => ({ ...passage, id, section, ...extra })
  const row = sourceModel({ citations: [
    p('a', '24', { law_status: 'repeal pending', section_state: 'repealed' }),
    p('b', '20', { section_state: 'amended' }),
    p('c', '7', {}),
  ] }).rows[0]
  assert.equal(row.passageLaw, 'repeal pending')
  assert.deepEqual(plain(row.passageSections), [{ section: '24', state: 'repealed' }, { section: '20', state: 'amended' }])
  // A labelled passage is still only retrieved, never verified.
  assert.equal(row.verification, 'none')
})
test('a section the audit already lists is not repeated from the passages', () => {
  const v = { ...verdict, section_status: [{ section: '24', status: 'repealed', by: 'X' }] }
  const row = sourceModel({ citations: [{ ...passage, section: '24', section_state: 'repealed' }], blocks: [{ kind: 'citation_audit', citations: [v] }] }).rows[0]
  assert.equal(row.deadSections.length, 1)
  assert.equal(row.passageSections.length, 0)
})

test('a quotation the cited section does not contain needs review', () => {
  const value = model({ ...verdict, quotes: [{ status: 'not_found', section: '75', quote: 'overtime after 208 hours in a month' }] })
  assert.equal(value.verified, 0)
  assert.equal(value.review, 1)
  assert.equal(value.rows[0].quoteIssues.length, 1)
})
test('a matching quotation keeps the library badge', () => {
  assert.equal(model({ ...verdict, quotes: [{ status: 'close', section: '75', quote: 'one and half times' }] }).verified, 1)
})
const caseVerdict = { kind: 'case', text: 'Wilson Masauso Zulu v Avondale Housing Project Limited (1982)', status: 'not_found' }
test('a case Levy does not hold but its judgments cite is known, not counted for review', () => {
  const value = sourceModel({ blocks: [{ kind: 'citation_audit', citations: [{ ...caseVerdict, known: { name: 'Wilson Masauso Zulu v Avondale Housing Project Limited', cited_by: 129, citation: '(1982) ZR 172' } }] }] })
  assert.equal(value.known, 1)
  assert.equal(value.review, 0)
  assert.equal(value.verified, 0)
})
test('a wrong year on a known case is reviewed', () => {
  const value = sourceModel({ blocks: [{ kind: 'citation_audit', citations: [{ ...caseVerdict, known: { name: 'x', cited_by: 129, citation: '(1982) ZR 172', year_conflict: true } }] }] })
  assert.equal(value.known, 0)
  assert.equal(value.review, 1)
})
test('a later departure is reviewed unless the answer names it', () => {
  const zubao = { kind: 'case', text: 'Zubao Harry Juma v First Quantum', status: 'verified', document_id: 'doc-z', title: 'Zubao', treatment: [{ treatment: 'departed from', judgment: 'Kingfred Phiri v Life Master Ltd', court: 'CAZ', year: 2024 }] }
  const run = (v) => sourceModel({ blocks: [{ kind: 'citation_audit', citations: [v] }] })
  assert.equal(run(zubao).review, 1)
  assert.equal(run({ ...zubao, treatment_acknowledged: true }).verified, 1)
})
