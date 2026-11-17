// Reading mode for the chat on a phone: scrolling down through an answer hides
// the dock so the answer gets the room, scrolling up brings it back.
//
// On a phone the header, the composer, the dock and the browser's own bar left
// about half the screen for the answer (screen recording, 17 Nov 2026). The
// same rule Safari uses for its toolbar: content moving up means "reading",
// content moving down means "I want the controls".
//
// Pure, so it can be tested without a DOM. conversation.tsx feeds it scroll
// positions and puts the result on <html data-chat-reading>; canopy.css moves
// the dock and the composer.

/** Pixels of continuous downward scroll before the dock hides. */
export const HIDE_AFTER = 32
/** Pixels of continuous upward scroll before it returns. */
export const SHOW_AFTER = 20
/** Within this many pixels of the top the dock is always shown. */
export const TOP_ZONE = 8

export type ReadingState = { last: number; travelled: number; reading: boolean }

export function readingStart(scrollTop = 0): ReadingState {
  return { last: scrollTop, travelled: 0, reading: false }
}

/**
 * The next state after a scroll event. `max` is scrollHeight - clientHeight.
 *
 * Distances add up since the last change of direction, so a thumb resting on
 * the glass does not flicker the dock. iOS reports positions past either end
 * while the page rubber-bands; those are clamped, or the bounce at the bottom
 * of an answer would read as scrolling up.
 */
export function readingStep(state: ReadingState, scrollTop: number, max: number): ReadingState {
  const y = Math.min(Math.max(scrollTop, 0), Math.max(max, 0))
  const delta = y - state.last
  if (max <= 0 || y <= TOP_ZONE) return { last: y, travelled: 0, reading: false }
  if (delta === 0) return state
  const travelled = Math.sign(delta) === Math.sign(state.travelled) ? state.travelled + delta : delta
  const reading = travelled > HIDE_AFTER ? true : travelled < -SHOW_AFTER ? false : state.reading
  return { last: y, travelled, reading }
}
