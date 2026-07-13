/* eslint-disable @typescript-eslint/no-explicit-any */
import { render, screen, waitFor } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import type { MapRef } from "react-map-gl/maplibre"

vi.mock("react-map-gl/maplibre", async () =>
  (await import("@/tests/helpers/mapGlMock")).mapGlMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", resolvedLanguage: "en", changeLanguage: () => Promise.resolve() },
  }),
}))
// Stub the heavy child components so this test isolates MapLibreMap's own logic
// (rAF poll, cinematic intro, easeTo, sky-update). Their internals are covered
// by their own tests.
vi.mock("@/components/map/BuildingMarker", () => ({ BuildingMarker: () => null }))
vi.mock("@/components/map/POIMarker", () => ({ POIMarker: () => null }))
vi.mock("@/components/map/EventMarker", () => ({ EventMarker: () => null }))
vi.mock("@/components/map/MapControls", () => ({ MapControls: () => null }))
vi.mock("@/components/map/WeatherParticles", () => ({ WeatherParticles: () => null }))

import { MapLibreMapComponent } from "@/components/map/MapLibreMap"

type MockMap = {
  loaded: ReturnType<typeof vi.fn>
  resize: ReturnType<typeof vi.fn>
  setSky: ReturnType<typeof vi.fn>
  jumpTo: ReturnType<typeof vi.fn>
  flyTo: ReturnType<typeof vi.fn>
  getCenter: ReturnType<typeof vi.fn>
  getZoom: ReturnType<typeof vi.fn>
  getPitch: ReturnType<typeof vi.fn>
  getBearing: ReturnType<typeof vi.fn>
}

function makeMap(): MockMap {
  return {
    loaded: vi.fn(() => true),
    resize: vi.fn(),
    setSky: vi.fn(),
    jumpTo: vi.fn(),
    flyTo: vi.fn(),
    getCenter: vi.fn(() => ({ lat: 55.7, lng: 37.8 })),
    getZoom: vi.fn(() => 16),
    getPitch: vi.fn(() => 45),
    getBearing: vi.fn(() => 0),
  }
}

function makeRef(map: MockMap) {
  return { current: { getMap: () => map, easeTo: vi.fn() } as unknown as MapRef }
}

const baseProps = {
  selectedBuilding: null,
  activeCategory: "all" as const,
  highlightedBuilding: null,
  onSelectBuilding: vi.fn(),
  onDeselectBuilding: vi.fn(),
}

describe("MapLibreMap", () => {
  let originalMatchMedia: any

  beforeEach(() => {
    originalMatchMedia = window.matchMedia
  })

  afterEach(() => {
    window.matchMedia = originalMatchMedia
  })

  it("renders the map application container with the a11y keyboard hint", () => {
    render(<MapLibreMapComponent {...baseProps} mapRef={makeRef(makeMap())} />)
    expect(screen.getByRole("application", { name: "a11y.mapContainer" })).toBeInTheDocument()
    expect(screen.getByText("a11y.mapKeyboardHint")).toBeInTheDocument()
  })

  it("on map-ready resizes, sets the sky, and runs the cinematic flyTo intro", async () => {
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))

    const map = makeMap()
    render(<MapLibreMapComponent {...baseProps} mapRef={makeRef(map)} isDark={false} />)
    await waitFor(() => expect(map.resize).toHaveBeenCalled())
    expect(map.setSky).toHaveBeenCalled()
    await waitFor(() => expect(map.flyTo).toHaveBeenCalled(), { timeout: 1500 })
  })

  it("jumps straight to a restored URL viewport instead of the intro", async () => {
    const map = makeMap()
    render(
      <MapLibreMapComponent
        {...baseProps}
        mapRef={makeRef(map)}
        urlInitialViewport={{ longitude: 37.8, latitude: 55.7, zoom: 17, pitch: 30, bearing: 90 }}
      />
    )
    await waitFor(() =>
      expect(map.jumpTo).toHaveBeenCalledWith(
        expect.objectContaining({ zoom: 17, pitch: 30, bearing: 90 })
      )
    )
    expect(map.flyTo).not.toHaveBeenCalled()
  })

  it("jumps (no animation) when the user prefers reduced motion", async () => {
    const map = makeMap()
    // Scoped spy + mockRestore — restoreAllMocks would wipe the global
    // setupTests matchMedia vi.fn() implementation for later tests.
    const mm = vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: true,
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    } as unknown as MediaQueryList)
    try {
      render(<MapLibreMapComponent {...baseProps} mapRef={makeRef(map)} />)
      await waitFor(() => expect(map.jumpTo).toHaveBeenCalled())
      expect(map.flyTo).not.toHaveBeenCalled()
    } finally {
      mm.mockRestore()
    }
  })

  it("eases to the selected building when one is chosen", async () => {
    const map = makeMap()
    const ref = makeRef(map)
    const easeTo = (ref.current as unknown as { easeTo: ReturnType<typeof vi.fn> }).easeTo
    render(<MapLibreMapComponent {...baseProps} mapRef={ref} selectedBuilding="ГУК" />)
    await waitFor(() =>
      expect(easeTo).toHaveBeenCalledWith(expect.objectContaining({ duration: 600 }))
    )
  })

  it("re-applies the sky on theme change", async () => {
    const map = makeMap()
    const ref = makeRef(map)
    const { rerender } = render(<MapLibreMapComponent {...baseProps} mapRef={ref} isDark={false} />)
    await waitFor(() => expect(map.setSky).toHaveBeenCalled())
    map.setSky.mockClear()
    rerender(<MapLibreMapComponent {...baseProps} mapRef={ref} isDark={true} />)
    await waitFor(() => expect(map.setSky).toHaveBeenCalled())
  })

  it("filters building markers by the active category without crashing", () => {
    render(
      <MapLibreMapComponent
        {...baseProps}
        mapRef={makeRef(makeMap())}
        activeCategory={"study" as typeof baseProps.activeCategory}
        mapEvents={[{ id: "e1", buildingId: "ГУК" } as never]}
      />
    )
    expect(screen.getByRole("application")).toBeInTheDocument()
  })
})
