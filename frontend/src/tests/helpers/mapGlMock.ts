import { createElement, type ReactNode } from "react"

type StubProps = { children?: ReactNode } & Record<string, unknown>

/**
 * Minimal jsdom-safe stub for `react-map-gl/maplibre` (Tier-3 STRETCH).
 *
 * Real maplibre-gl needs WebGL/canvas which jsdom lacks. Markers/popups render
 * their children inside a plain <div>; the forwarded `ref` is intentionally NOT
 * applied, so a marker's `markerRef.current` stays null and
 * `useStripMaplibreMarkerChrome` early-returns (its 3 removeAttribute lines live
 * in a separate file and stay uncovered — an acceptable trade).
 *
 * Usage:
 *   vi.mock("react-map-gl/maplibre", async () =>
 *     (await import("@/tests/helpers/mapGlMock")).mapGlMock())
 */
function MapGlStub({ children }: StubProps) {
  return createElement("div", null, children)
}
MapGlStub.displayName = "MapGlStub"

export function mapGlMock() {
  return {
    Map: MapGlStub,
    Marker: MapGlStub,
    Popup: MapGlStub,
    Source: MapGlStub,
    Layer: MapGlStub,
    useMap: () => ({ current: null }),
  }
}
