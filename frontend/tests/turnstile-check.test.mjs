import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import vm from 'node:vm'

// The guest browser check (src/lib/turnstile-check.ts), driven with a fake
// Cloudflare widget, fake <script> tags and a fake clock.
//
// The failures it guards against were real: guests on Android Chrome and
// Windows Edge waited through two silent 30 s checks and were turned away
// with "no token, client timeout", because the tick box Cloudflare asked for
// was squeezed, hidden behind the keyboard or composer, and unexplained.
const src = readFileSync(new URL('../src/lib/turnstile-check.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText
const sandbox = { exports: {}, module: { exports: {} }, Promise, Error, Set }
vm.createContext(sandbox)
vm.runInContext(js, sandbox)
const { createTurnstileCheck, cardFor, WAIT_MS, SLOW_MS, PERSON_MS } = sandbox.exports

function world({ width = 390 } = {}) {
  let now = 0
  let seq = 0
  const timers = new Map()
  const scripts = []
  const widgets = []
  const blurred = []
  const api = {
    render(el, opts) {
      const w = { id: `w${widgets.length + 1}`, el, opts, resets: 0, removed: false }
      widgets.push(w)
      return w.id
    },
    reset(id) {
      widgets.find((w) => w.id === id).resets++
    },
    remove(id) {
      widgets.find((w) => w.id === id).removed = true
    },
  }
  const win = { innerWidth: width }
  const doc = {
    head: { appendChild: (s) => scripts.push(s) },
    createElement() {
      const handlers = { load: [], error: [] }
      return {
        src: '',
        async: false,
        defer: false,
        removed: false,
        addEventListener(type, fn) {
          handlers[type].push(fn)
        },
        remove() {
          this.removed = true
        },
        fire(type) {
          handlers[type].forEach((fn) => fn())
        },
      }
    },
    querySelector: () => scripts.filter((s) => !s.removed).at(-1) ?? null,
    activeElement: { blur: () => blurred.push(now) },
  }
  const env = {
    win,
    doc,
    setTimeout(fn, ms) {
      const id = ++seq
      timers.set(id, { at: now + ms, fn })
      return id
    },
    clearTimeout(id) {
      timers.delete(id)
    },
    now: () => now,
  }
  const check = createTurnstileCheck('site-key', 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit', env)
  check.setHolder({ holder: true })
  check.setEnabled(true)
  return {
    check,
    scripts,
    widgets,
    blurred,
    loadScript() {
      win.turnstile = api
      scripts.at(-1).fire('load')
    },
    failScript() {
      scripts.at(-1).fire('error')
    },
    widget: () => widgets.at(-1),
    async advance(ms) {
      const end = now + ms
      for (;;) {
        const due = [...timers.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0]
        if (!due) break
        timers.delete(due[0])
        now = due[1].at
        due[1].fn()
        await Promise.resolve()
      }
      now = end
      await Promise.resolve()
    },
  }
}

// Resolve state of a promise without awaiting it forever.
async function peek(p) {
  let out = 'pending'
  p.then((v) => (out = { value: v }))
  await Promise.resolve()
  await Promise.resolve()
  return out
}

test('a challenge that wants a tick shows a labelled card and waits for the person, not 30 s', async () => {
  const w = world()
  w.check.prime() // typing started
  w.loadScript()
  assert.equal(w.widget().opts.appearance, 'interaction-only')
  assert.equal(w.check.getView().card, 'hidden', 'nothing drawn while Cloudflare is happy')

  w.widget().opts['before-interactive-callback']()
  assert.equal(w.check.getView().card, 'interactive')

  const p = w.check.getToken() // the person sends
  assert.equal(w.widget().resets, 0, 'the box they are about to tick is not reset under them')
  assert.equal(w.blurred.length, 1, 'the keyboard is closed so the box is not behind it')

  await w.advance(WAIT_MS + 5_000)
  assert.equal(await peek(p), 'pending', 'still waiting for the tick after 30 s')
  assert.equal(w.check.getView().card, 'interactive')

  w.widget().opts['after-interactive-callback']()
  w.widget().opts.callback('token-1')
  assert.deepEqual(await peek(p), { value: 'token-1' })
  assert.equal(w.check.getView().card, 'hidden')
  assert.equal(w.check.getView().showing, false)
})

test('an unticked box ends in a failed card that says why, after the person had time', async () => {
  const w = world()
  const p = w.check.getToken()
  w.loadScript()
  w.widget().opts['before-interactive-callback']()
  await w.advance(PERSON_MS + 1)
  assert.deepEqual(await peek(p), { value: null })
  assert.equal(w.check.lastError(), 'timeout:interactive')
  assert.equal(w.check.getView().card, 'failed')
  assert.equal(w.check.getView().reason, 'timeout:interactive')
})

test('a slow check says so after a few seconds instead of a silent spinner', async () => {
  const w = world()
  const p = w.check.getToken() // sent before the script arrived
  assert.equal(w.scripts.length, 1)
  await w.advance(SLOW_MS - 1)
  assert.equal(w.check.getView().card, 'hidden')
  await w.advance(1)
  assert.equal(w.check.getView().card, 'checking')
  await w.advance(WAIT_MS)
  assert.deepEqual(await peek(p), { value: null })
  assert.equal(w.check.lastError(), 'timeout:script', 'the log can tell a script that never arrived from an unticked box')
  assert.equal(w.check.getView().card, 'failed')
})

test('a script that fails to load fails fast, and Try again fetches it afresh', async () => {
  const w = world()
  const p = w.check.getToken()
  w.failScript()
  assert.deepEqual(await peek(p), { value: null }, 'no 30 s wait on a dead script')
  assert.equal(w.check.lastError(), 'script_error')
  assert.equal(w.check.getView().card, 'failed')
  assert.equal(w.scripts[0].removed, true)

  w.check.restart() // Try again
  assert.equal(w.scripts.length, 2, 'a new <script> tag, not a wait on the dead one')
  const q = w.check.getToken()
  w.loadScript()
  assert.equal(w.widget().opts.appearance, 'always', 'the retry is drawn on screen')
  assert.equal(w.check.getView().card, 'checking')
  w.widget().opts.callback('token-2')
  assert.deepEqual(await peek(q), { value: 'token-2' })
  assert.equal(w.check.getView().card, 'hidden')
})

test('a send after a failed script load fetches the script again by itself', async () => {
  const w = world()
  w.check.prime()
  w.failScript() // failed while typing: nobody is told yet
  assert.equal(w.check.getView().card, 'hidden')
  const p = w.check.getToken()
  assert.equal(w.scripts.length, 2)
  w.loadScript()
  w.widget().opts.callback('token-3')
  assert.deepEqual(await peek(p), { value: 'token-3' })
})

test('a token solved while typing is used once; the next question asks the widget again', async () => {
  const w = world()
  w.check.prime()
  w.loadScript()
  w.widget().opts.callback('banked')
  assert.equal(await w.check.getToken(), 'banked')
  assert.equal(w.widget().resets, 0)
  const p = w.check.getToken()
  assert.equal(w.widget().resets, 1, 'a spent token is replaced by resetting the widget')
  w.widget().opts.callback('fresh')
  assert.deepEqual(await peek(p), { value: 'fresh' })
})

test('a widget error fails at once with its code', async () => {
  const w = world()
  w.check.prime()
  w.loadScript()
  const p = w.check.getToken()
  w.widget().opts['error-callback'](300030)
  assert.deepEqual(await peek(p), { value: null })
  assert.equal(w.check.lastError(), '300030')
  assert.equal(w.check.getView().card, 'failed')
})

test('the server refusing a token shows the failed card; Not now puts it away', () => {
  const w = world()
  w.check.prime()
  w.loadScript()
  w.check.fail()
  assert.equal(w.check.getView().card, 'failed')
  w.check.dismiss()
  assert.equal(w.check.getView().card, 'hidden')
  assert.equal(w.widget().removed, true)
})

test('narrow phones get the compact widget so it fits the card', () => {
  const narrow = world({ width: 320 })
  narrow.check.prime()
  narrow.loadScript()
  assert.equal(narrow.widget().opts.size, 'compact')
  const usual = world({ width: 390 })
  usual.check.prime()
  usual.loadScript()
  assert.equal(usual.widget().opts.size, 'normal')
})

test('signed in (or no site key): no token, no script', async () => {
  const w = world()
  w.check.setEnabled(false)
  assert.equal(await w.check.getToken(), null)
  w.check.prime()
  assert.equal(w.scripts.length, 0)
})

test('the card is never shown once a token is in hand', () => {
  for (const interactive of [true, false])
    for (const failed of [true, false])
      assert.equal(cardFor({ showing: false, interactive, failed, visible: true, waiting: true, slow: true }), 'hidden')
})
