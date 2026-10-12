// Renders the final pay and gratuity cards from real backend output
// (tests/fixtures/final-pay.json, written by services/final_pay.py for the
// HR user's case of 6 October 2026).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { createRequire } from 'node:module'
import ts from 'typescript'

const require = createRequire(import.meta.url)
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')

function load(path, extra = {}) {
  const source = fs.readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 },
  })
  const exported = {}
  const req = (name) => (name in extra ? extra[name] : require(name))
  vm.runInNewContext(outputText, { exports: exported, require: req, module: { exports: exported } })
  return exported
}

const payroll = load('components/chat/payroll-card.tsx')
const { FinalPayCard } = load('components/chat/final-pay-card.tsx', { './payroll-card': payroll })
const fixture = JSON.parse(fs.readFileSync(new URL('./fixtures/final-pay.json', import.meta.url), 'utf8'))
const html = (breakdown) => renderToStaticMarkup(React.createElement(FinalPayCard, { breakdown }))

test('final pay leads with the net and shows the set-off as a deduction', () => {
  const out = html(fixture.final_pay)
  assert.match(out, /Final pay/)
  assert.match(out, /Resignation · long-term contract · last day 15 Jan 2026/)
  assert.match(out, /Net K0\.00/)
  assert.match(out, /K1,306\.45/)
  assert.match(out, /−K1,757\.48/)
  assert.match(out, /Left for the employer to claim, not deduct/)
  assert.match(out, /K942\.52/)
  assert.match(out, /s\.53\(5\) and s\.68\(1\)\(a\)/)
})

test('a contested gratuity is tagged and kept out of the total', () => {
  const out = html(fixture.final_pay)
  assert.match(out, /Contested/)
  assert.match(out, /Conditional or contested, not counted/)
  assert.match(out, /K241\.94/)
})

test('gratuity to date shows the balance and the end-of-contract figure', () => {
  const out = html(fixture.gratuity)
  assert.match(out, /Gratuity to date/)
  assert.match(out, /Balance K13,000\.00/)
  assert.match(out, /At the end of the contract/)
  assert.match(out, /para 40/)
})
