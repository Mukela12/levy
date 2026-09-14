/** The photograph changes once an hour, anchored to the moment the visitor last chose one. */
export const SCENE_INTERVAL = 60 * 60 * 1000

export interface ScenePreference {
  index: number
  anchor: number
  auto: boolean
}

export function sceneAt(preference: ScenePreference, count: number, now = Date.now()): number {
  if (!count) return 0
  const passed = preference.auto ? Math.max(0, Math.floor((now - preference.anchor) / SCENE_INTERVAL)) : 0
  return (((preference.index + passed) % count) + count) % count
}

export function nextSceneDelay(preference: ScenePreference, now = Date.now()): number {
  return Math.max(1, SCENE_INTERVAL - (Math.max(0, now - preference.anchor) % SCENE_INTERVAL))
}
