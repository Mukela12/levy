'use client'

/**
 * Canopy's new-conversation surface: a Zambian photograph behind a glass
 * composer, the three welcome actions, and a footer that credits the
 * photographer and lets the visitor change or pause the view. Everything the
 * page needs to actually send (composer, trial nudge, attachment flows) is
 * passed in, so this component owns presentation only.
 */

import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react'
import { ArrowUpRight, Check, ChevronRight, ExternalLink, type LucideIcon } from 'lucide-react'
import { InFocus } from './in-focus'
import { CanopyModal } from './modal'
import { SCENES, PHOTO_SIZES, photoSrc, photoSrcSet, type Scene } from './scene-collection'
import { nextSceneDelay, sceneAt, SCENE_INTERVAL, type ScenePreference } from './scene-clock'

const PREF_KEY = 'levy-canopy-scenery'
const PREF_EVENT = 'levy-canopy-scenery-change'
const SERVER_PREFERENCE: ScenePreference = { index: 0, anchor: 0, auto: true }

// The stored preference is read through an external-store subscription, so
// the server render (no storage) and the first client render agree, and no
// state is set inside an effect.
let cachedRaw: string | null | undefined
let cachedPreference: ScenePreference = SERVER_PREFERENCE
function readPreference(): ScenePreference {
  let raw: string | null = null
  try {
    raw = window.localStorage.getItem(PREF_KEY)
  } catch {
    return cachedPreference
  }
  if (raw === cachedRaw) return cachedPreference
  cachedRaw = raw
  let next: ScenePreference = { index: 0, anchor: 0, auto: true }
  if (raw) {
    try {
      const p = JSON.parse(raw) as Partial<ScenePreference>
      if (typeof p.index === 'number' && Number.isFinite(p.index) && Number.isInteger(p.index) && typeof p.anchor === 'number' && Number.isFinite(p.anchor) && p.anchor >= 0) {
        next = { index: p.index, anchor: p.anchor, auto: p.auto !== false }
      }
    } catch {
      /* keep the default */
    }
  }
  cachedPreference = next
  return next
}
function subscribePreference(cb: () => void) {
  window.addEventListener('storage', cb)
  window.addEventListener(PREF_EVENT, cb)
  return () => {
    window.removeEventListener('storage', cb)
    window.removeEventListener(PREF_EVENT, cb)
  }
}
function writePreference(next: ScenePreference) {
  try {
    window.localStorage.setItem(PREF_KEY, JSON.stringify(next))
  } catch {
    /* storage unavailable: the choice lasts for this page only */
    cachedRaw = JSON.stringify(next)
    cachedPreference = next
  }
  window.dispatchEvent(new Event(PREF_EVENT))
}

export function ScenePicture({ scene, className = '', priority = false, thumbnail = false }: { scene: Scene; className?: string; priority?: boolean; thumbnail?: boolean }) {
  const sizes = thumbnail ? '(max-width: 600px) 140px, 320px' : PHOTO_SIZES
  return (
    <picture className={className} style={{ ['--photo-position' as string]: scene.focus }}>
      <img
        src={photoSrc(scene.id, thumbnail ? 640 : 1600)}
        srcSet={photoSrcSet(scene.id)}
        sizes={sizes}
        alt={scene.description}
        loading={priority ? 'eager' : 'lazy'}
        fetchPriority={priority ? 'high' : 'auto'}
        decoding="async"
        draggable={false}
      />
    </picture>
  )
}

function PhotoCredit({ scene, full = false }: { scene: Scene; full?: boolean }) {
  return (
    <div className={'cp-photo-credit' + (full ? ' is-full' : '')}>
      <a href={scene.source} target="_blank" rel="noreferrer">{scene.author}</a>
      {scene.authorUrl && (
        <>
          {' · '}
          <a href={scene.authorUrl} target="_blank" rel="noreferrer">delso.photo</a>
        </>
      )}
      {' · '}
      <a href={scene.licenseUrl} target="_blank" rel="noreferrer">{scene.license}</a>
      {full && (
        <>
          <p>
            {scene.dimensions[0].toLocaleString()} × {scene.dimensions[1].toLocaleString()} px original. Display copies are resized only, with no edits. The phone and tablet framing follows the landscape; the full photograph is on the source page.
          </p>
          <a className="cp-photo-original" href={scene.source} target="_blank" rel="noreferrer">
            View the full-resolution photograph <ExternalLink size={13} />
          </a>
        </>
      )}
    </div>
  )
}

export interface WelcomeStarter {
  label: string
  description: string
  icon: LucideIcon
}

export interface WelcomeSceneProps {
  greeting: string
  /** Accepted for the caller's convenience; the welcome no longer renders an anonymous nudge. */
  isAnonymous?: boolean
  starters: WelcomeStarter[]
  onStarter: (question: string) => void
  composer: ReactNode
  below?: ReactNode
  hasDraft?: boolean
}

/** Re-anchor the rotation on a manual pick; lives at module scope so the
 * clock read stays out of render. */
function commitScene(
  index: number,
  len: number,
  preference: ScenePreference,
  setNow: (n: number) => void,
  setPreference: (p: ScenePreference) => void,
) {
  const t = Date.now()
  setNow(t)
  setPreference({ ...preference, index: ((index % len) + len) % len, anchor: t })
}

export function WelcomeScene({ greeting, starters, onStarter, composer, below, hasDraft }: WelcomeSceneProps) {
  const preference = useSyncExternalStore(subscribePreference, readPreference, () => SERVER_PREFERENCE)
  const hydrated = useSyncExternalStore(subscribePreference, () => true, () => false)
  const [now, setNow] = useState(() => Date.now())
  const [showExamples, setShowExamples] = useState(false)
  const [focusHidden, setFocusHidden] = useState(false)
  const restoreFocusRef = useRef<HTMLButtonElement>(null)
  const [gallery, setGallery] = useState(false)
  const setPreference = (next: ScenePreference) => writePreference(next)

  const scenes = SCENES
  const currentIndex = sceneAt(preference, scenes.length, now)
  const current = scenes[currentIndex]
  const [previous, setPrevious] = useState<Scene | null>(null)
  // Filled on the first hydrated render, so the photo the visitor sees first
  // never crossfades in from the build-time scene.
  const lastScene = useRef<Scene | null>(null)

  // Hourly tick, paused when the tab is hidden and resumed on return.
  useEffect(() => {
    if (!hydrated) return
    let timer: ReturnType<typeof setTimeout> | undefined
    const tick = () => {
      setNow(Date.now())
      if (preference.auto) timer = setTimeout(tick, nextSceneDelay(preference))
    }
    timer = setTimeout(tick, 0)
    const wake = () => {
      if (document.visibilityState === 'visible') {
        clearTimeout(timer)
        tick()
      }
    }
    document.addEventListener('visibilitychange', wake)
    return () => {
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', wake)
    }
  }, [preference, hydrated])

  // Crossfade: keep the outgoing photograph for 950ms.
  useEffect(() => {
    if (!hydrated) return
    if (!lastScene.current) { lastScene.current = current; return }
    if (lastScene.current.id === current.id) return
    const outgoing = lastScene.current
    lastScene.current = current
    setPrevious(outgoing)
    const t = setTimeout(() => setPrevious(null), 950)
    return () => clearTimeout(t)
  }, [current, hydrated])

  const handleSelect = (index: number) => commitScene(index, scenes.length, preference, setNow, setPreference)
  function toggleAuto() {
    const t = Date.now()
    setNow(t)
    setPreference({ index: currentIndex, anchor: t, auto: !preference.auto })
  }
  const nextChange = useMemo(() => {
    const at = preference.anchor + (Math.max(0, Math.floor((now - preference.anchor) / SCENE_INTERVAL)) + 1) * SCENE_INTERVAL
    return new Date(at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }, [preference.anchor, now])

  return (
    <section className={`cp-welcome scene-${current.id}`} aria-label="New conversation">
     <div className="cp-welcome-frame">
      <div className={'cp-scene-stage' + (previous ? ' is-changing' : '')} aria-hidden="true">
        {hydrated && previous && <ScenePicture scene={previous} className="cp-scene-image is-previous" />}
        {hydrated && <ScenePicture key={current.id} scene={current} className="cp-scene-image is-current" priority />}
      </div>

      <div className="cp-welcome-content">
        <div className="cp-welcome-signature">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/levy-logo.svg" alt="" width={38} height={38} draggable={false} />
          <span>levy</span>
        </div>
        <p className="cp-welcome-greeting">{greeting}</p>
        <h1>{current.headline}</h1>

        {composer}
        {below}

        {/* Stays mounted and folds away while a draft is typed, so the
            composer and footer never jump when it leaves or returns. */}
        <div className={'cp-welcome-below' + (hasDraft ? ' is-collapsed' : '')} inert={hasDraft ? true : undefined}>
          <div className="cp-welcome-below-clip">
            {!focusHidden ? <InFocus onChoose={onStarter} onDismiss={() => { setFocusHidden(true); requestAnimationFrame(() => restoreFocusRef.current?.focus({ preventScroll: true })) }} /> : <div className="cp-welcome-secondary">
              <button ref={restoreFocusRef} type="button" onClick={() => setFocusHidden(false)}>Show a question<ChevronRight size={15} /></button>
              <button type="button" onClick={() => setShowExamples(true)} aria-haspopup="dialog" aria-expanded={showExamples}>
                Try an example
                <ChevronRight size={15} className={showExamples ? 'is-open' : ''} />
              </button>
            </div>}
          </div>
        </div>

        {showExamples && (
          <CanopyModal title="Try an example" onClose={() => setShowExamples(false)}>
          <p>Choose a starting point. You can edit it before sending.</p>
          <div className="cp-example-list">
            {starters.map((s) => (
              <button key={s.label} type="button" onClick={() => { setShowExamples(false); onStarter(s.description) }}>
                <s.icon size={18} />
                <span><strong>{s.label}</strong><small>{s.description}</small></span>
                <ArrowUpRight size={15} />
              </button>
            ))}
          </div>
          </CanopyModal>
        )}
      </div>

      <footer className="cp-scene-footer">
        <div className="cp-scene-location">
          <button type="button" className="cp-scene-caption" onClick={() => setGallery(true)} aria-label={`Choose a background. Current: ${current.title}`}>
            <span className="cp-scene-caption-title">{current.title}</span>
            <span>{current.caption}</span>
          </button>
          <PhotoCredit scene={current} />
        </div>
      </footer>
     </div>

      {gallery && (
        <CanopyModal title="A view of Zambia" onClose={() => setGallery(false)} wide>
              <p className="cp-muted">Choose a view, or let the collection change quietly once an hour.</p>
              <div className="cp-scenery-grid">
                {scenes.map((scene, i) => (
                  <article className="cp-scenery-item" key={scene.id}>
                    <button type="button" className={'cp-scenery-choice' + (scene.id === current.id ? ' is-selected' : '')} aria-pressed={scene.id === current.id} aria-label={`Use ${scene.title}`} onClick={() => handleSelect(i)}>
                      <ScenePicture scene={scene} thumbnail />
                      <div>
                        <strong>{scene.title}</strong>
                        {scene.id === current.id && <Check size={17} />}
                        <small>{scene.caption}</small>
                      </div>
                    </button>
                    <PhotoCredit scene={scene} />
                  </article>
                ))}
              </div>
              <details className="cp-scenery-details">
                <summary>About “{current.title}”</summary>
                <PhotoCredit scene={current} full />
              </details>
              <div className="cp-scenery-settings">
                <label>
                  <input type="checkbox" checked={preference.auto} onChange={toggleAuto} />
                  <span>
                    Change the background every hour
                    <small>{preference.auto ? `Next change at ${nextChange}` : 'The selected view will stay in place.'}</small>
                  </span>
                </label>
                <button type="button" className="cp-btn primary" onClick={() => setGallery(false)}>Done <Check size={16} /></button>
              </div>
              <p className="cp-scenery-note">Real photographs, framed for your screen. Credits and the untouched originals are linked above.</p>
        </CanopyModal>
      )}
    </section>
  )
}
