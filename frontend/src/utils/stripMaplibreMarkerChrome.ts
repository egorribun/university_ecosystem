import type { RefObject } from "react"
import { useEffect } from "react"
import type { MarkerInstance } from "react-map-gl/maplibre"

/**
 * Wave 116 polish — axe `nested-interactive` suppression for MapLibre markers.
 *
 * Background: maplibre-gl's `Marker` class unconditionally sets `role="button"`
 * + `aria-label="Map marker"` on its wrapper element (inside its constructor,
 * independent of whether a click handler is attached). When the child we render
 * inside the wrapper is itself interactive (role="button" + tabIndex + onClick
 * for accessibility), axe flags `nested-interactive` on every single marker —
 * a serious violation that drops the /map a11y score sharply.
 *
 * This hook runs on mount and strips the `role="button"` + `aria-label` from
 * the outer wrapper DOM node via `marker.getElement()`. The inner child stays
 * the only interactive element in the a11y tree, carrying the rich localized
 * aria-label (e.g. "Выбран Главный учебный корпус. 8 этажей, 37 аудиторий.").
 *
 * Why not drop the inner `role="button"` instead: the outer wrapper's
 * `aria-label` is hardcoded to "Map marker" by maplibre-gl core and not
 * parameterised; we cannot set a useful accessible name on it. Stripping the
 * outer and keeping the inner is the only way to preserve per-marker context.
 *
 * Safe against re-renders: the DOM element is the same across renders (maplibre
 * reuses the wrapper) so `removeAttribute` is idempotent.
 */
export function useStripMaplibreMarkerChrome(
  markerRef: RefObject<MarkerInstance | null>,
): void {
  useEffect(() => {
    const marker = markerRef.current
    if (!marker) return
    const el = marker.getElement()
    if (!el) return
    el.removeAttribute("role")
    el.removeAttribute("aria-label")
    el.removeAttribute("tabindex")
  })
}

// Non-hook variant used inside existing useEffect blocks where composing a new
// dedicated hook is heavier than a direct call.
export function stripMaplibreMarkerChrome(marker: MarkerInstance | null): void {
  if (!marker) return
  const el = marker.getElement()
  if (!el) return
  el.removeAttribute("role")
  el.removeAttribute("aria-label")
  el.removeAttribute("tabindex")
}
