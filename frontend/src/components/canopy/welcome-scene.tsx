'use client'

/**
 * Canopy's new-conversation surface: a Zambian photograph behind a glass
 * composer, the three welcome actions, and a footer that credits the
 * photographer and lets the visitor change or pause the view. Everything the
 * page needs to actually send (composer, trial nudge, attachment flows) is
 * passed in, so this component owns presentation only.
 */

import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react'
import { ArrowUpRight, Check, ChevronLeft, ChevronRight, ExternalLink, FolderPlus, Image as ImageIcon, Pause, Play, type LucideIcon } from 'lucide-react'
import { InFocus } from './in-focus'
import { CanopyModal } from './modal'
import { SCENES, photoSrc, photoSrcSet, type Scene } from './scene-collection'
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
  const sizes = thumbnail ? '(max-width: 600px) 140px, 320px' : '(max-width: 1100px) 100vw, calc(100vw - 300px)'
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
  isAnonymous: boolean
  starters: WelcomeStarter[]
  onStarter: (question: string) => void
  /** Opens the attach flow. Absent for signed-out visitors, who see a sign-in hint instead. */
  onAddDocument?: () => void
  composer: ReactNode
  below?: ReactNode
  hasDraft?: boolean
}

export function WelcomeScene({ greeting, isAnonymous, starters, onStarter, onAddDocument, composer, below, hasDraft }: WelcomeSceneProps) {
  const preference = useSyncExternalStore(subscribePreference, readPreference, () => SERVER_PREFERENCE)
  const hydrated = useSyncExternalStore(subscribePreference, () => true, () => false)
  const [now, setNow] = useState(() => Date.now())
  const [showExamples, setShowExamples] = useState(false)
  const [gallery, setGallery] = useState(false)
  const setPreference = (next: ScenePreference) => writePreference(next)

  const scenes = SCENES
  const currentIndex = sceneAt(preference, scenes.length, now)
  const current = scenes[currentIndex]
  const [previous, setPrevious] = useState<Scene | null>(null)
  const lastScene = useRef<Scene>(current)

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
    if (lastScene.current.id === current.id) return
    const outgoing = lastScene.current
    lastScene.current = current
    setPrevious(outgoing)
    const t = setTimeout(() => setPrevious(null), 950)
    return () => clearTimeout(t)
  }, [current])

  function select(index: number) {
    const t = Date.now()
    setNow(t)
    setPreference({ ...preference, index: ((index % scenes.length) + scenes.length) % scenes.length, anchor: t })
  }
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
        {previous && <ScenePicture scene={previous} className="cp-scene-image is-previous" />}
        <ScenePicture key={current.id} scene={current} className="cp-scene-image is-current" priority />
      </div>

      <div className="cp-welcome-content">
        <div className="cp-welcome-signature">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/levy-logo.svg" alt="" width={38} height={38} draggable={false} />
          <span>levy</span>
        </div>
        <p className="cp-welcome-greeting">{greeting}</p>
        <h1>A clearer place to begin.</h1>

        {composer}
        {below}

        <div className="cp-welcome-secondary">
          {!hasDraft && <InFocus onChoose={onStarter} />}
          <button type="button" onClick={() => setShowExamples(true)} aria-haspopup="dialog" aria-expanded={showExamples}>
            Try an example
            <ChevronRight size={15} className={showExamples ? 'is-open' : ''} />
          </button>
          {onAddDocument ? (
            <button type="button" onClick={onAddDocument}>
              <FolderPlus size={18} aria-hidden="true" />
              Add a document
            </button>
          ) : null}
        </div>
        {isAnonymous && (
          <p className="cp-welcome-anon">
            Try a question. No account needed. <a href="/auth/login">Sign in to save your chats</a>.
          </p>
        )}

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
        <div className="cp-scene-controls">
          <button type="button" aria-label="Previous background" onClick={() => select(currentIndex - 1)}><ChevronLeft size={17} /></button>
          <button type="button" className="cp-scene-count" aria-label="Choose background" onClick={() => setGallery(true)}>
            <ImageIcon size={16} />
            <span>{String(currentIndex + 1).padStart(2, '0')} / {String(scenes.length).padStart(2, '0')}</span>
          </button>
          <button type="button" aria-label="Next background" onClick={() => select(currentIndex + 1)}><ChevronRight size={17} /></button>
          <span className="cp-scene-divider" aria-hidden="true" />
          <button type="button" className="cp-scene-auto" aria-pressed={preference.auto} aria-label={preference.auto ? 'Pause hourly backgrounds' : 'Resume hourly backgrounds'} title={preference.auto ? 'Changes once per hour' : 'Keep this background'} onClick={toggleAuto}>
            {preference.auto ? <Pause size={14} /> : <Play size={14} />}
            <span>{preference.auto ? 'Hourly' : 'Paused'}</span>
          </button>
        </div>
      </footer>
     </div>

      {gallery && (
        <CanopyModal title="A view of Zambia" onClose={() => setGallery(false)} wide>
              <p className="cp-muted">Choose a view, or let the collection change quietly once an hour.</p>
              <div className="cp-scenery-grid">
                {scenes.map((scene, i) => (
                  <article className="cp-scenery-item" key={scene.id}>
                    <button type="button" className={'cp-scenery-choice' + (scene.id === current.id ? ' is-selected' : '')} aria-pressed={scene.id === current.id} aria-label={`Use ${scene.title}`} onClick={() => select(i)}>
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
