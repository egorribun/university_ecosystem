/**
 * Tiny shared store for view-transition hero morphing between
 * news list and detail pages. Enables BOTH directions:
 *
 * Forward (list→detail): NewsCardView sets transitioning=true on pointerDown
 * Back (detail→list):    NewsDetail sets heroId on mount; card reads it during render
 *
 * No reactivity needed — value is read once during the render that
 * produces the view-transition snapshot.
 */

let _heroId: string | null = null

/** Called by NewsDetail on mount — stores which card to morph back to. */
export function setNewsHeroId(id: string | null) {
  _heroId = id
}

/** Read by NewsCardHero during render — returns the ID to morph. */
export function getNewsHeroId(): string | null {
  return _heroId
}

/** Clear after transition completes (prevents stale matches). */
export function clearNewsHeroId() {
  _heroId = null
}
