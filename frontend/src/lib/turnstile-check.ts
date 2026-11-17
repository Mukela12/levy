// The guest browser check (Cloudflare Turnstile), without React, so the
// timing and failure paths can be tested in node with a fake widget and a fake
// clock (tests/turnstile-check.test.mjs). use-turnstile.ts wraps it in a hook.
//
// Why it is built this way (17 Nov 2026). Guests who failed the check all
// logged the same thing: no token, the client's 30 s wait ran out, and no
// widget callback had fired. Reproduced with Cloudflare's "always interactive"
// test key: Cloudflare was asking for a tick, and the person never saw a
// usable box.
//   - The widget lived in a fixed holder at `left: 50%`, which shrinks to half
//     the screen. On a phone that is 187 px for a 300 px widget, so the box was
//     cut off, unlabelled, and sat over the composer or the photo credit.
//   - With the keyboard open on Android it was drawn behind the keyboard.
//   - The page said "Thinking…" for 30 s, retried silently for another 30 s,
//     and only then offered sign-in, in a footer that phones hide.
//   - A Turnstile script that failed to load was never noticed; the retry
//     waited on the same dead <script> tag.
// Now: when Cloudflare wants a tick, a labelled card shows the full-size box
// and waits for the person; a slow check says so after a few seconds; a
// failure says why and offers Try again and sign-in at once; a failed script
// is fetched again. Nothing here decides who passes. The server still accepts
// only a token Cloudflare verifies, or the pass it issued after one.

export type CheckCard = 'hidden' | 'checking' | 'interactive' | 'failed'

export type CheckView = {
  /** A widget is rendered. */
  ready: boolean
  /** The check may draw. False once a token is in hand, so a solved widget does not linger. */
  showing: boolean
  /** What the on-screen card says. */
  card: CheckCard
  /** Why the last attempt produced no token (see lastError). */
  reason: string | null
}

type TurnstileApi = {
  render: (el: unknown, opts: Record<string, unknown>) => string
  reset: (id: string) => void
  remove: (id: string) => void
}

type ScriptTag = {
  src: string
  async: boolean
  defer: boolean
  addEventListener: (type: 'load' | 'error', fn: () => void) => void
  remove: () => void
}

export type CheckEnv = {
  win: { turnstile?: TurnstileApi; innerWidth: number }
  doc: {
    head: { appendChild: (el: ScriptTag) => unknown }
    createElement: (tag: 'script') => ScriptTag
    querySelector: (selector: string) => ScriptTag | null
    activeElement: unknown
  }
  setTimeout: (fn: () => void, ms: number) => unknown
  clearTimeout: (handle: unknown) => void
  now: () => number
}

/** How long a send waits for a token when Cloudflare has not asked for a tick. */
export const WAIT_MS = 30_000
/** When a waiting send shows the "checking" card instead of a silent spinner. */
export const SLOW_MS = 8_000
/** How long a send waits once Cloudflare has put a box in front of the person. */
export const PERSON_MS = 180_000
/** Below this width the 300 px widget does not fit the card; use the compact one. */
export const COMPACT_BELOW = 344

const SCRIPT_SELECTOR = 'script[src^="https://challenges.cloudflare.com/turnstile/v0/api.js"]'

export function cardFor(s: {
  showing: boolean
  interactive: boolean
  failed: boolean
  visible: boolean
  waiting: boolean
  slow: boolean
}): CheckCard {
  if (!s.showing) return 'hidden'
  if (s.failed) return 'failed'
  if (s.interactive) return 'interactive'
  if (s.visible || (s.waiting && s.slow)) return 'checking'
  return 'hidden'
}

export function createTurnstileCheck(siteKey: string, scriptSrc: string, env: CheckEnv) {
  let enabled = false
  // Load and render only once a question is under way (prime) or sent.
  let wanted = false
  // Drawn whether or not Cloudflare asks for interaction (after a restart).
  let visible = false
  let holder: unknown = null
  let widgetId: string | null = null
  // A challenge is running on the widget and has not reported back yet.
  let pending = false
  let banked: string | null = null
  let script: 'none' | 'loading' | 'loaded' | 'failed' = 'none'
  // Why the last attempt produced no token: the widget's error code,
  // "script_error", "expired", "challenge_timeout", "unsupported",
  // "no_widget", or "timeout:<stage>" where stage is script, running,
  // interactive or no_widget. Sent with a failed request so the server log
  // says why a visitor was turned away.
  let lastError: string | null = null
  let interactive = false
  let failed = false
  let showing = true
  let slow = false
  let waiter: { resolve: (t: string | null) => void; started: number; timer: unknown; slowTimer: unknown } | null = null

  const listeners = new Set<() => void>()
  const compute = (): CheckView => ({
    ready: !!widgetId,
    showing,
    card: cardFor({ showing, interactive, failed, visible, waiting: !!waiter, slow }),
    reason: failed ? lastError : null,
  })
  let view = compute()

  function emit() {
    const next = compute()
    if (
      next.ready === view.ready &&
      next.showing === view.showing &&
      next.card === view.card &&
      next.reason === view.reason
    )
      return
    view = next
    listeners.forEach((l) => l())
  }

  // Close an on-screen keyboard: on Android it covers the bottom of the page,
  // and a check the person has to tick must not sit behind it.
  function blurActive() {
    const el = env.doc.activeElement as { blur?: () => void } | null
    try {
      el?.blur?.()
    } catch {
      // nothing focused that can blur
    }
  }

  function stopTimers(w: NonNullable<typeof waiter>) {
    env.clearTimeout(w.timer)
    env.clearTimeout(w.slowTimer)
  }

  function finish(t: string | null, reason?: string) {
    const w = waiter
    if (!w) return
    waiter = null
    stopTimers(w)
    slow = false
    if (!t) {
      if (reason) lastError = reason
      failed = true
    }
    w.resolve(t)
  }

  // Deliver a widget result to whoever is waiting, or bank it for the next getToken().
  function deliver(t: string | null) {
    pending = false
    if (t) {
      showing = false
      failed = false
    }
    if (waiter) finish(t)
    else banked = t
    emit()
  }

  function timeoutReason() {
    if (interactive) return 'timeout:interactive'
    if (script !== 'loaded') return 'timeout:script'
    if (!widgetId) return 'timeout:no_widget'
    return 'timeout:running'
  }

  function arm(ms: number) {
    const w = waiter
    if (!w) return
    w.timer = env.setTimeout(() => {
      if (waiter !== w) return
      const waited = env.now() - w.started
      // Cloudflare put a box in front of the person: give them time to tick it
      // rather than failing the request under them.
      if (interactive && waited < PERSON_MS) {
        arm(PERSON_MS - waited)
        return
      }
      finish(null, timeoutReason())
      emit()
    }, ms)
  }

  function removeWidget() {
    const id = widgetId
    widgetId = null
    pending = false
    interactive = false
    if (id && env.win.turnstile) {
      try {
        env.win.turnstile.remove(id)
      } catch {
        // widget already gone
      }
    }
  }

  function render() {
    if (!enabled || !wanted || !holder || widgetId || !env.win.turnstile) return
    try {
      widgetId = env.win.turnstile.render(holder, {
        sitekey: siteKey,
        // Only draws when Cloudflare wants interaction, unless restarted.
        appearance: visible ? 'always' : 'interaction-only',
        size: env.win.innerWidth < COMPACT_BELOW ? 'compact' : 'normal',
        // A banked token expires after 5 minutes. Auto-refresh would pop a
        // fresh challenge while someone is only reading; getToken() asks for
        // a new one if and when it is actually needed.
        'refresh-expired': 'never',
        callback: (t: string) => {
          lastError = null
          interactive = false
          deliver(t)
        },
        'error-callback': (code?: string | number) => {
          lastError = code ? String(code) : 'error'
          interactive = false
          deliver(null)
        },
        'expired-callback': () => {
          lastError = 'expired'
          deliver(null)
        },
        'timeout-callback': () => {
          lastError = 'challenge_timeout'
          interactive = false
          deliver(null)
        },
        'unsupported-callback': () => {
          lastError = 'unsupported'
          deliver(null)
        },
        'before-interactive-callback': () => {
          interactive = true
          if (waiter) blurActive()
          emit()
        },
        'after-interactive-callback': () => {
          interactive = false
          emit()
        },
      })
      pending = true
    } catch {
      widgetId = null
      lastError = 'render_error'
      if (waiter) finish(null, 'render_error')
    }
    emit()
  }

  function onScriptLoad() {
    if (!env.win.turnstile) {
      onScriptError()
      return
    }
    script = 'loaded'
    render()
  }

  function onScriptError() {
    script = 'failed'
    lastError = 'script_error'
    // A tag that failed never fires 'load' again; the next attempt adds a new one.
    env.doc.querySelector(SCRIPT_SELECTOR)?.remove()
    // Fail now rather than after the full wait. Nobody is told while they are
    // still typing; the next send fetches the script again.
    if (waiter) finish(null, 'script_error')
    emit()
  }

  function ensure() {
    if (!enabled || !wanted || !holder) return
    if (env.win.turnstile) {
      script = 'loaded'
      render()
      return
    }
    if (script === 'loading') return
    const existing = env.doc.querySelector(SCRIPT_SELECTOR)
    if (existing && script === 'none') {
      // Added by an earlier mount and still on its way.
      script = 'loading'
      existing.addEventListener('load', onScriptLoad)
      existing.addEventListener('error', onScriptError)
      return
    }
    // Fetch afresh (after a failure, or a restart that dropped a slow tag).
    existing?.remove()
    const s = env.doc.createElement('script')
    s.src = scriptSrc
    s.async = true
    s.defer = true
    s.addEventListener('load', onScriptLoad)
    s.addEventListener('error', onScriptError)
    script = 'loading'
    env.doc.head.appendChild(s)
  }

  return {
    subscribe(fn: () => void) {
      listeners.add(fn)
      return () => {
        listeners.delete(fn)
      }
    },
    getView: () => view,
    lastError: () => lastError,

    /** Callback ref for the element the widget draws into. */
    setHolder(el: unknown) {
      if (el === holder) return
      if (!el) removeWidget()
      holder = el
      ensure()
      emit()
    },

    setEnabled(on: boolean) {
      if (on === enabled) return
      enabled = on
      if (!on) {
        removeWidget()
        finish(null, 'disabled')
        failed = false
      } else {
        ensure()
      }
      emit()
    },

    /** A question is under way: load and solve while the person types. */
    prime() {
      wanted = true
      ensure()
      emit()
    },

    /**
     * Resolve a single-use token: the one banked by an earlier solve if there
     * is one, otherwise the running or a fresh challenge. Resolves null, with
     * lastError saying why, rather than hanging.
     */
    getToken(): Promise<string | null> {
      if (!enabled) return Promise.resolve(null)
      // A banked token is used first. Deliberately NOT re-arming here: the
      // server's pass covers later questions, and a reset now is what made the
      // checkbox reappear mid-answer.
      if (banked) {
        const t = banked
        banked = null
        return Promise.resolve(t)
      }
      const prev = waiter
      if (prev) {
        waiter = null
        stopTimers(prev)
        prev.resolve(null)
      }
      lastError = null
      return new Promise<string | null>((resolve) => {
        const w = { resolve, started: env.now(), timer: null as unknown, slowTimer: null as unknown }
        waiter = w
        failed = false
        slow = false
        showing = true
        w.slowTimer = env.setTimeout(() => {
          if (waiter !== w) return
          slow = true
          emit()
        }, SLOW_MS)
        arm(WAIT_MS)
        if (interactive) blurActive()
        if (!widgetId) {
          // Not rendered yet (or its script failed): load it now, and its
          // first solve resolves this wait.
          wanted = true
          ensure()
        } else if (!pending) {
          // The last token was spent: ask the widget for a new one. A
          // challenge still running (say, one the person has not ticked yet)
          // is left alone, not restarted under them.
          try {
            if (!env.win.turnstile) throw new Error('no turnstile')
            env.win.turnstile.reset(widgetId)
            pending = true
          } catch {
            // The widget was torn down: fail fast, there is nothing to wait for.
            finish(null, 'no_widget')
          }
        }
        emit()
      })
    },

    /** Start again with a fresh widget, drawn visibly; fetch the script again if it never arrived. */
    restart() {
      removeWidget()
      banked = null
      if (!env.win.turnstile) {
        env.doc.querySelector(SCRIPT_SELECTOR)?.remove()
        script = 'none'
      }
      visible = true
      showing = true
      wanted = true
      failed = false
      ensure()
      emit()
    },

    /** The server refused what the check produced: show the failed card. */
    fail() {
      failed = true
      showing = true
      emit()
    },

    /** Put the failed card away. The next send renders a fresh widget. */
    dismiss() {
      if (waiter) return
      removeWidget()
      banked = null
      failed = false
      visible = false
      wanted = false
      emit()
    },
  }
}

export type TurnstileCheck = ReturnType<typeof createTurnstileCheck>
