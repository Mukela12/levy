import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const output = ts.transpileModule(fs.readFileSync(new URL('../src/lib/cite-links.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText
const exported = {}
vm.runInNewContext(output, { exports: exported, require: () => ({}), Map, Set, RegExp, Number, Math })
const { buildCiteIndex, resolveCite, rehypeCiteLinks } = exported

const employment = { document_id: 'doc-emp', act_name: 'Employment Code Act, 2019 (No. 3 of 2019)', section: '53', page_start: 35, page_end: 35 }
const judgment = { document_id: 'doc-app', act_name: 'APP No. 36 of 2020', section: '', page_start: 16, page_end: 16 }
const sources = () => buildCiteIndex({ citations: [employment, judgment] })

const render = (text, srcs = sources()) => {
  const tree = { type: 'root', children: [{ type: 'element', tagName: 'p', children: [{ type: 'text', value: text }] }] }
  rehypeCiteLinks(srcs)()(tree)
  return tree.children[0].children
}
const links = (nodes) => nodes.filter((n) => n.type === 'element').map((n) => ({
  documentId: n.properties['data-cite'], page: n.properties['data-page'], text: n.children[0].value,
}))

test('a named Act with a section links to the passage page', () => {
  const [link] = links(render('The notice period is 30 days [Employment Code Act, Section 53].'))
  assert.equal(link.documentId, 'doc-emp')
  assert.equal(link.page, '35')
  assert.equal(link.text, '[Employment Code Act, Section 53]')
})

test('a bare section binds to the Act named earlier in the prose', () => {
  const [link] = links(render('Under the Employment Code Act, 2019 an employer must give notice [s. 53(1)].'))
  assert.equal(link.documentId, 'doc-emp')
})

test('a bare section with no Act in hand stays plain text', () => {
  assert.equal(links(render('The rule appears at [s. 132(2)] of that statute.')).length, 0)
})

test('a named Act the answer never used is not linked to the Act in hand', () => {
  const nodes = render('Under the Employment Code Act notice is due [Subordinate Courts Act, Section 38].')
  assert.equal(links(nodes).length, 0)
})

test('draft placeholders and bare years are never links', () => {
  for (const text of ['Signed by [FIRM NAME] for the plaintiff.', 'decided in [2007] by the court', 'pay [AMOUNT] within 14 days'])
    assert.equal(links(render(text)).length, 0, text)
})

test('a judgment citation links at its page', () => {
  const [link] = links(render('The court said so [APP No. 36 of 2020, p. 16].'))
  assert.equal(link.documentId, 'doc-app')
  assert.equal(link.page, '16')
})

test('code and existing links are left alone', () => {
  const tree = { type: 'root', children: [
    { type: 'element', tagName: 'code', children: [{ type: 'text', value: '[Employment Code Act, Section 53]' }] },
    { type: 'element', tagName: 'a', properties: { href: 'https://x.test' }, children: [{ type: 'text', value: '[Employment Code Act, Section 53]' }] },
  ] }
  rehypeCiteLinks(sources())()(tree)
  for (const node of tree.children) {
    assert.equal(node.children.length, 1)
    assert.equal(node.children[0].type, 'text')
  }
})

test('the surrounding sentence survives the split', () => {
  const nodes = render('See [Employment Code Act, Section 53] for notice.')
  assert.equal(nodes.map((n) => (n.type === 'text' ? n.value : n.children[0].value)).join(''),
    'See [Employment Code Act, Section 53] for notice.')
})

test('an audit verdict alone is enough to link', () => {
  const srcs = buildCiteIndex({ blocks: [{ kind: 'citation_audit', citations: [
    { text: 'Children’s Code Act No. 12 of 2022', kind: 'statute', status: 'verified', document_id: 'doc-child', title: 'The Children’s Code Act, 2022' },
  ] }] })
  const [link] = links(render('A child is under 18 [Children’s Code Act, Section 2].', srcs))
  assert.equal(link.documentId, 'doc-child')
})

test('resolveCite reports the section it matched', () => {
  const found = resolveCite('Employment Code Act, Section 53', sources())
  assert.equal(found.link.section, '53')
  assert.equal(found.link.documentId, 'doc-emp')
})
