import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import vm from 'node:vm'

const src = readFileSync(new URL('../src/lib/chat-attachments.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText
const sandbox = { exports: {}, module: { exports: {} } }
vm.createContext(sandbox)
vm.runInContext(js, sandbox)
const { attachedDocsOf, historyFor, earlierAttachments, CARRY_TURNS } = sandbox.exports

const PDF = { id: 'c1081b60-3f59-4328-aba0-4f94162b9f46', title: 'Overtime claim' }
const attaching = (content, docs = [PDF]) => ({ role: 'user', content, blocks: [{ kind: 'attachments', docs }] })
const user = (content) => ({ role: 'user', content })
const levy = (content) => ({ role: 'assistant', content, blocks: [{ kind: 'text', text: content }] })

test('the 23 October follow-up carries the PDF attached one message earlier', () => {
  // "i attached a pdf document" went out with no attachment and no trace of one.
  const thread = [attaching('What does this say about overtime?'), levy('Nothing was pasted or attached.')]
  assert.deepEqual(plain(earlierAttachments(thread, 0)), [PDF])
})

test('the attachment rides along for three more messages, then stops', () => {
  assert.equal(CARRY_TURNS, 3)
  const thread = [attaching('Review this'), levy('Done.')]
  for (let n = 1; n <= 3; n++) {
    assert.deepEqual(plain(earlierAttachments(thread, 0)), [PDF], `follow-up ${n}`)
    thread.push(user(`Follow-up ${n}`), levy('Answer.'))
  }
  assert.deepEqual(plain(earlierAttachments(thread, 0)), [])
})

test('a message with its own attachment carries nothing earlier', () => {
  const thread = [attaching('Review this'), levy('Done.')]
  assert.deepEqual(plain(earlierAttachments(thread, 1)), [])
})

test('the newest attachment wins over an older one', () => {
  const contract = { id: 'd2', title: 'Contract' }
  const thread = [attaching('First', [PDF]), levy('A.'), attaching('Second', [contract]), levy('B.')]
  assert.deepEqual(plain(earlierAttachments(thread, 0)), [contract])
})

test('the history names each message attachments, with their ids', () => {
  const history = historyFor([attaching('Review this'), levy('Reviewed.'), user('Thanks'), { role: 'assistant', content: '' }])
  assert.deepEqual(plain(history), [
    { role: 'user', content: `Review this\n\n[Attached to this message: "Overtime claim" (document_id ${PDF.id})]` },
    { role: 'assistant', content: 'Reviewed.' },
    { role: 'user', content: 'Thanks' },
  ])
})

test('malformed attachment blocks are ignored', () => {
  assert.deepEqual(plain(attachedDocsOf({ role: 'user', content: 'x', blocks: [null, { kind: 'attachments', docs: [{}, { id: '' }, { id: 'ok' }] }] })),
    [{ id: 'ok', title: 'Document' }])
  assert.deepEqual(plain(attachedDocsOf({ role: 'user', content: 'x', blocks: null })), [])
})

// Values made inside the vm carry its realm's prototypes; compare their JSON.
function plain(value) {
  return JSON.parse(JSON.stringify(value))
}
