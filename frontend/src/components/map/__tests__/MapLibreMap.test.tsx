import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { createElement, type ReactNode } from "react"
import type { MapRef } from "react-map-gl/maplibre"

const translationState = vi.hoisted(() => ({ resolvedLanguage: "en" as string | undefined }))
const renderedMapProps = vi.hoisted(() => ({ current: {} as Record<string, unknown> }))

vi.mock("react-map-gl/maplibre", async () => {
  const base = (await import("@/tests/helpers/mapGlMock")).mapGlMock()
  const invoke = (callback: unknown, ...args: unknown[]) => {
    if (typeof callback === "function") callback(...args)
  }
  const MapWithEvents = (props: Record<string, unknown>) => {
    renderedMapProps.current = props
    const { children, onClick, onMoveEnd } = props
    return createElement(
      "div",
      null,
      createElement(
        "button",
        { type: "button", "data-testid": "map-click", onClick: () => invoke(onClick) },
        "map click"
      ),
      createElement(
        "button",
        {
          type: "button",
          "data-testid": "map-move-end",
          onClick: () => invoke(onMoveEnd, { originalEvent: { type: "mouse" } }),
        },
        "map move"
      ),
      createElement(
        "button",
        {
          type: "button",
          "data-testid": "map-move-end-programmatic",
          onClick: () => invoke(onMoveEnd, {}),
        },
        "programmatic move"
      ),
      children as ReactNode
    )
  }
  return { ...base, Map: MapWithEvents }
})
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: "en",
      resolvedLanguage: translationState.resolvedLanguage,
      changeLanguage: () => Promise.resolve(),
    },
  }),
}))
// Stub the heavy child components so this test isolates MapLibreMap's own logic
// (rAF poll, cinematic intro, easeTo, sky-update). Their internals are covered
// by their own tests.
vi.mock("@/components/map/BuildingMarker", () => ({
  BuildingMarker: (props: Record<string, unknown>) => {
    const building = props.building as { letter: string }
    const invoke = (callback: unknown) => {
      if (typeof callback === "function") callback()
    }
    return createElement(
      "div",
      null,
      createElement(
        "button",
        {
          type: "button",
          "data-testid": `building-open-${building.letter}`,
          onClick: () => invoke(props.onPopupOpen),
        },
        "building open"
      ),
      createElement(
        "button",
        {
          type: "button",
          "data-testid": `building-close-${building.letter}`,
          onClick: () => invoke(props.onPopupClose),
        },
        "building close"
      )
    )
  },
}))
vi.mock("@/components/map/POIMarker", () => ({
  POIMarker: (props: Record<string, unknown>) => {
    const invoke = (callback: unknown) => {
      if (typeof callback === "function") callback()
    }
    return createElement(
      "div",
      null,
      createElement(
        "button",
        { type: "button", "data-testid": "poi-open", onClick: () => invoke(props.onPopupOpen) },
        "poi open"
      ),
      createElement(
        "button",
        { type: "button", "data-testid": "poi-close", onClick: () => invoke(props.onPopupClose) },
        "poi close"
      )
    )
  },
}))
vi.mock("@/components/map/EventMarker", () => ({
  EventMarker: (props: Record<string, unknown>) => {
    const invoke = (callback: unknown) => {
      if (typeof callback === "function") callback()
    }
    return createElement(
      "div",
      null,
      createElement(
        "button",
        { type: "button", "data-testid": "event-open", onClick: () => invoke(props.onPopupOpen) },
        "event open"
      ),
      createElement(
        "button",
        { type: "button", "data-testid": "event-close", onClick: () => invoke(props.onPopupClose) },
        "event close"
      )
    )
  },
}))
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
    renderedMapProps.current = {}
  })

  afterEach(() => {
    window.matchMedia = originalMatchMedia
    translationState.resolvedLanguage = "en"
  })

  it("renders the map application container with the a11y keyboard hint", () => {
    render(<MapLibreMapComponent {...baseProps} mapRef={makeRef(makeMap())} />)
    expect(screen.getByRole("application", { name: "a11y.mapContainer" })).toBeInTheDocument()
    expect(screen.getByText("a11y.mapKeyboardHint")).toBeInTheDocument()
  })

  it("contains gestures locally and does not retain a shared MapLibre instance", () => {
    render(<MapLibreMapComponent {...baseProps} mapRef={makeRef(makeMap())} />)

    const region = screen.getByRole("application", { name: "a11y.mapContainer" })
    expect(region).toHaveStyle({ overscrollBehavior: "contain" })
    expect(renderedMapProps.current.reuseMaps).not.toBe(true)
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
    const requestFrame = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback) => {
        callback(0)
        return 1
      })
    const map = makeMap()
    const ref = makeRef(map)
    try {
      const { rerender } = render(
        <MapLibreMapComponent {...baseProps} mapRef={ref} isDark={false} />
      )
      await waitFor(() => expect(map.setSky).toHaveBeenCalled())
      map.setSky.mockClear()
      rerender(<MapLibreMapComponent {...baseProps} mapRef={ref} isDark={true} />)
      await waitFor(() => expect(map.setSky).toHaveBeenCalled())
      expect(map.resize).toHaveBeenCalledTimes(2)
    } finally {
      requestFrame.mockRestore()
    }
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

  it("dispatches map, marker-popup, weather, and move-end interactions", () => {
    const onDeselectBuilding = vi.fn()
    const onMapMoveEnd = vi.fn()
    render(
      <MapLibreMapComponent
        {...baseProps}
        onDeselectBuilding={onDeselectBuilding}
        onMapMoveEnd={onMapMoveEnd}
        mapRef={makeRef(makeMap())}
        weatherCondition="rain"
        mapEvents={[{ id: "event-1", buildingId: "ГУК" } as never]}
      />
    )

    fireEvent.click(screen.getByTestId("map-click"))
    fireEvent.click(screen.getByTestId("map-move-end-programmatic"))
    fireEvent.click(screen.getByTestId("map-move-end"))
    fireEvent.click(screen.getByTestId("map-move-end-programmatic"))
    fireEvent.click(screen.getByTestId("building-open-ГУК"))
    fireEvent.click(screen.getByTestId("building-close-ГУК"))
    fireEvent.click(screen.getAllByTestId("poi-open")[0]!)
    fireEvent.click(screen.getAllByTestId("poi-close")[0]!)
    fireEvent.click(screen.getByTestId("event-open"))
    fireEvent.click(screen.getByTestId("event-close"))

    expect(onDeselectBuilding).toHaveBeenCalled()
    expect(onMapMoveEnd).toHaveBeenCalledTimes(2)
    expect(onMapMoveEnd).toHaveBeenCalledWith({
      zoom: 16,
      latitude: 55.7,
      longitude: 37.8,
      pitch: 45,
      bearing: 0,
    })
  })

  it("uses the base language and skips an unknown selected building", () => {
    translationState.resolvedLanguage = undefined
    const map = makeMap()
    const ref = makeRef(map)
    const easeTo = (ref.current as unknown as { easeTo: ReturnType<typeof vi.fn> }).easeTo

    render(
      <MapLibreMapComponent
        {...baseProps}
        mapRef={ref}
        selectedBuilding={"missing-building" as never}
      />
    )

    expect(screen.getByRole("application")).toBeInTheDocument()
    expect(easeTo).not.toHaveBeenCalled()
  })

  it("stops a pending map-readiness poll after unmount", () => {
    let pendingFrame: FrameRequestCallback | undefined
    const requestAnimationFrame = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback) => {
        pendingFrame = callback
        return 1
      })
    const cancelAnimationFrame = vi
      .spyOn(window, "cancelAnimationFrame")
      .mockImplementation(() => undefined)

    try {
      const { unmount } = render(<MapLibreMapComponent {...baseProps} />)
      pendingFrame?.(0)
      fireEvent.click(screen.getByTestId("map-move-end"))
      unmount()
      pendingFrame?.(0)
      expect(cancelAnimationFrame).toHaveBeenCalled()
    } finally {
      requestAnimationFrame.mockRestore()
      cancelAnimationFrame.mockRestore()
    }
  })

  it("does not start the intro after its timeout was cancelled by unmount", () => {
    const map = makeMap()
    let pendingFrame: FrameRequestCallback | undefined
    let introCallback: (() => void) | undefined
    const requestAnimationFrame = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback) => {
        pendingFrame = callback
        return 1
      })
    const realSetTimeout = globalThis.setTimeout
    const setTimeout = vi.spyOn(globalThis, "setTimeout").mockImplementation((handler, timeout) => {
      if (timeout === 300) {
        introCallback = handler as unknown as () => void
        return 99 as unknown as ReturnType<typeof globalThis.setTimeout>
      }
      return realSetTimeout(handler, timeout)
    })

    try {
      const { unmount } = render(<MapLibreMapComponent {...baseProps} mapRef={makeRef(map)} />)
      pendingFrame?.(0)
      expect(map.resize).toHaveBeenCalled()
      expect(introCallback).toBeDefined()
      unmount()
      introCallback?.()
      expect(map.flyTo).not.toHaveBeenCalled()
    } finally {
      requestAnimationFrame.mockRestore()
      setTimeout.mockRestore()
    }
  })
})
