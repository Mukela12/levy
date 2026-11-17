import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import vm from 'node:vm'

// Reading mode (src/lib/reading-mode.ts): on a phone the dock hides while the
// reader scrolls down through an answer and returns when they scroll up.
const src = readFileSync(new URL('../src/lib/reading-mode.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText
const sandbox = { exports: {}, module: { exports: {} }, Math }
vm.createContext(sandbox)
vm.runInContext(js, sandbox)
const { readingStart, readingStep, HIDE_AFTER, SHOW_AFTER } = sandbox.exports

const MAX = 4000
const scroll = (positions, from = 0) => positions.reduce((s, y) => readingStep(s, y, MAX), readingStart(from))

test('reading down an answer hides the dock, and only after a real scroll', () => {
  assert.equal(scroll([20]).reading, false)                       // a nudge is not reading
  assert.equal(scroll([20, 40, 60, 100, 160, 240]).reading, true)
  assert.equal(HIDE_AFTER > SHOW_AFTER, true)                     // easier to get the controls back than to lose them
})

test('scrolling up a little brings the dock back', () => {
  const down = scroll([100, 200, 300, 400])
  assert.equal(down.reading, true)
  assert.equal(readingStep(down, 392, MAX).reading, true)          // a wobble of the thumb
  const up = [390, 380, 370].reduce((s, y) => readingStep(s, y, MAX), down)
  assert.equal(up.reading, false)
})

test('a change of direction starts the count again', () => {
  // down 30, up 10, down 30: never 32 in one direction
  assert.equal(scroll([130, 120, 150], 100).reading, false)
})

test('the top of the conversation always shows the dock', () => {
  const down = scroll([100, 200, 300])
  assert.equal(readingStep(down, 4, MAX).reading, false)
  assert.equal(readingStep(down, 0, MAX).reading, false)
})

test('a conversation too short to scroll never hides it', () => {
  assert.equal(readingStep(readingStart(0), 60, 0).reading, false)
})

test('the bounce at the end of an answer on iOS is not scrolling up', () => {
  const end = scroll([3800, 3900, 4000])
  assert.equal(end.reading, true)
  // overscroll past the end and settle back: positions beyond max are clamped
  const bounced = [4060, 4090, 4040, 4000].reduce((s, y) => readingStep(s, y, MAX), end)
  assert.equal(bounced.reading, true)
  // and the bounce above the top never produces a negative position
  assert.equal(readingStep(readingStart(0), -40, MAX).reading, false)
})

test('the stylesheet moves the dock and the composer, and nothing else animates', () => {
  const css = readFileSync(new URL('../src/styles/canopy.css', import.meta.url), 'utf8')
  assert.match(css, /\[data-chat-reading\] \.cp-dock \{[^}]*visibility: hidden/)
  assert.match(css, /\[data-chat-reading\] \.cp-harness-composer \{ transform: translateY\(/)
  const rule = css.match(/\n  \.cp-dock \{ transition: ([^}]*)\}/)[1]
  assert.equal(/\ball\b|height|bottom|top/.test(rule), false)      // transform, opacity and visibility only
  assert.match(css, /prefers-reduced-motion: reduce\) \{ \.cp-dock,/)
  // the answer must not show through between the composer and the dock
  assert.match(css, /\.cp-harness-composer::before \{[^}]*background: var\(--cp-bg\)/)
})
