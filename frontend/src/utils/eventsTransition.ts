/**
 * Tiny shared store for view-transition hero morphing between
 * events list and detail pages. Same pattern as newsTransition.ts.
 *
 * Forward (list→detail): EventCardView sets transitioning=true on pointerDown
 * Back (detail→list):    EventDetail sets heroId on mount; card reads it during render
 *
 * IMPORTANT: Only ONE element may have viewTransitionName="events-hero"
 * at any time (CLAUDE.md constraint).
 */

let _heroId: string | null = null

/** Called by EventDetail on mount — stores which card to morph back to. */
export function setEventsHeroId(id: string | null) {
  _heroId = id
}

/** Read by EventCardHero during render — returns the ID to morph. */
export function getEventsHeroId(): string | null {
  return _heroId
}

/** Clear after transition completes (prevents stale matches). */
export function clearEventsHeroId() {
  _heroId = null
}
