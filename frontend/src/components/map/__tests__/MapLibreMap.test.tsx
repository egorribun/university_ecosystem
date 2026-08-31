import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { createElement, type ReactNode } from "react"
import type { MapRef } from "react-map-gl/maplibre"

const translationState = vi.hoisted(() => ({
  language: "en",
  resolvedLanguage: "en" as string | undefined,
  namespaces: [] as string[],
}))
const deviceState = vi.hoisted(() => ({ lowPower: false }))
const renderedMapProps = vi.hoisted(() => ({ current: {} as Record<string, unknown> }))
const renderedLayerProps = vi.hoisted(() => ({ current: {} as Record<string, unknown> }))
const renderedMarkerProps = vi.hoisted(() => ({
  buildings: [] as Record<string, unknown>[],
  pois: [] as Record<string, unknown>[],
  events: [] as Record<string, unknown>[],
}))
const renderedOverlayProps = vi.hoisted(() => ({
  controls: [] as Record<string, unknown>[],
  weather: [] as Record<string, unknown>[],
}))

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
  const Layer = (props: Record<string, unknown>) => {
    renderedLayerProps.current = props
    return null
  }
  return { ...base, Map: MapWithEvents, Layer }
})
vi.mock("react-i18next", () => ({
  useTranslation: (namespace: string) => {
    translationState.namespaces.push(namespace)
    return {
      t: (key: string) => key,
      i18n: {
        language: translationState.language,
        resolvedLanguage: translationState.resolvedLanguage,
        changeLanguage: () => Promise.resolve(),
      },
    }
  },
}))
vi.mock("@/utils/deviceCapabilities", () => ({
  isLowPowerDevice: () => deviceState.lowPower,
}))
// Stub the heavy child components so this test isolates MapLibreMap's own logic
// (rAF poll, cinematic intro, easeTo, sky-update). Their internals are covered
// by their own tests.
vi.mock("@/components/map/BuildingMarker", () => ({
  BuildingMarker: (props: Record<string, unknown>) => {
    renderedMarkerProps.buildings.push(props)
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
    renderedMarkerProps.pois.push(props)
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
    renderedMarkerProps.events.push(props)
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
vi.mock("@/components/map/MapControls", () => ({
  MapControls: (props: Record<string, unknown>) => {
    renderedOverlayProps.controls.push(props)
    return null
  },
}))
vi.mock("@/components/map/WeatherParticles", () => ({
  WeatherParticles: (props: Record<string, unknown>) => {
    renderedOverlayProps.weather.push(props)
    return null
  },
}))

let MapLibreMapComponent: (typeof import("@/components/map/MapLibreMap"))["MapLibreMapComponent"]

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
  project: ReturnType<typeof vi.fn>
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
    project: vi.fn(([longitude, latitude]: [number, number]) => ({
      x: longitude * 10_000,
      y: latitude * 10_000,
    })),
  }
}

function makeRef(map: MockMap) {
  return { current: { getMap: () => map, easeTo: vi.fn() } as unknown as MapRef }
}

function latestBy<T extends Record<string, unknown>>(
  values: readonly T[],
  predicate: (value: T) => boolean
) {
  for (let index = values.length - 1; index >= 0; index -= 1) {
    const value = values[index]
    if (value && predicate(value)) return value
  }
  return undefined
}

function latestBuilding(letter: string) {
  return latestBy(
    renderedMarkerProps.buildings,
    (props) => (props.building as { letter: string }).letter === letter
  )
}

function latestPoi(id: string) {
  return latestBy(renderedMarkerProps.pois, (props) => (props.poi as { id: string }).id === id)
}

function latestEvent(id: string) {
  return latestBy(renderedMarkerProps.events, (props) => (props.event as { id: string }).id === id)
}

function currentMoveEndHandler() {
  return renderedMapProps.current.onMoveEnd as (event: { originalEvent?: unknown }) => void
}

const baseProps = {
  selectedBuilding: null,
  activeCategory: "all" as const,
  highlightedBuilding: null,
  onSelectBuilding: vi.fn(),
  onDeselectBuilding: vi.fn(),
}

describe("MapLibreMap", () => {
  it("starts at a campus-detail zoom that keeps interactive markers separated", () => {
    render(<MapLibreMapComponent {...baseProps} />)

    expect(renderedMapProps.current.initialViewState).toEqual({
      longitude: 37.81478,
      latitude: 55.7144,
      zoom: 17,
      pitch: 0,
      bearing: -20,
    })
    expect(renderedMapProps.current.mapStyle).toBe("https://tiles.openfreemap.org/styles/bright")
    expect(renderedLayerProps.current).toEqual({
      id: "3d-buildings-generic",
      type: "fill-extrusion",
      source: "openmaptiles",
      "source-layer": "building",
      minzoom: 15,
      paint: {
        "fill-extrusion-color": [
          "interpolate",
          ["linear"],
          ["get", "render_height"],
          0,
          "#d1d5db",
          50,
          "#9ca3af",
          100,
          "#6b7280",
        ],
        "fill-extrusion-height": [
          "interpolate",
          ["linear"],
          ["zoom"],
          15,
          0,
          16,
          ["get", "render_height"],
        ],
        "fill-extrusion-base": ["get", "render_min_height"],
        "fill-extrusion-opacity": 0.5,
      },
    })
    expect(renderedMapProps.current.style).toEqual({
      width: "100%",
      height: "100%",
      minHeight: "inherit",
      borderRadius: 12,
    })
    expect(renderedMapProps.current.attributionControl).toBe(false)
    expect(renderedMapProps.current.maxPitch).toBe(70)
    expect(renderedOverlayProps.controls).toHaveLength(0)
  })
  let originalMatchMedia: any

  beforeEach(async () => {
    originalMatchMedia = window.matchMedia
    deviceState.lowPower = false
    renderedMapProps.current = {}
    renderedLayerProps.current = {}
    renderedMarkerProps.buildings = []
    renderedMarkerProps.pois = []
    renderedMarkerProps.events = []
    renderedOverlayProps.controls = []
    renderedOverlayProps.weather = []
    translationState.language = "en"
    translationState.namespaces = []
    vi.resetModules()
    ;({ MapLibreMapComponent } = await import("@/components/map/MapLibreMap"))
  })

  afterEach(() => {
    window.matchMedia = originalMatchMedia
    translationState.language = "en"
    translationState.resolvedLanguage = "en"
  })

  it("renders the map application container with the a11y keyboard hint", () => {
    render(<MapLibreMapComponent {...baseProps} mapRef={makeRef(makeMap())} />)
    const application = screen.getByRole("application", { name: "a11y.mapContainer" })
    expect(application).toHaveAttribute("aria-roledescription", "a11y.mapRoleDescription")
    expect(screen.getByText("a11y.mapKeyboardHint")).toHaveClass("sr-only")
    expect(translationState.namespaces).toContain("map")
    expect(renderedOverlayProps.controls.length).toBeGreaterThan(0)
    expect(renderedOverlayProps.controls.every((props) => props.mapRef !== undefined)).toBe(true)
    expect(document.querySelector(".map-controls-positioner")).toHaveStyle({ bottom: "12px" })
    const attribution = screen.getByRole("link", { name: "© OpenStreetMap" })
    expect(attribution).toHaveAttribute("href", "https://www.openstreetmap.org/copyright")
    expect(attribution).toHaveAttribute("target", "_blank")
    expect(attribution).toHaveAttribute("rel", "noopener noreferrer")
    expect(attribution).toHaveStyle({ color: "var(--text-tertiary)" })
  })

  it("uses the dark map style without changing the MapLibre interaction contract", () => {
    render(<MapLibreMapComponent {...baseProps} mapRef={makeRef(makeMap())} isDark />)

    expect(renderedMapProps.current.mapStyle).toBe("https://tiles.openfreemap.org/styles/dark")
    expect(renderedMapProps.current.attributionControl).toBe(false)
    expect(renderedMapProps.current.maxPitch).toBe(70)
  })

  it("contains gestures locally and does not retain a shared MapLibre instance", () => {
    render(<MapLibreMapComponent {...baseProps} mapRef={makeRef(makeMap())} />)

    const region = screen.getByRole("application", { name: "a11y.mapContainer" })
    expect(region).toHaveStyle({ overscrollBehavior: "contain" })
    expect(renderedMapProps.current.reuseMaps).not.toBe(true)
  })

  it("assigns distinct deterministic offsets to collocated focusable markers", () => {
    render(<MapLibreMapComponent {...baseProps} mapRef={makeRef(makeMap())} />)

    const poiOffset = (id: string) => {
      const marker = renderedMarkerProps.pois.find(
        (props) => (props.poi as { id: string }).id === id
      )
      return marker?.offset
    }

    expect(poiOffset("gorzdrav")).toEqual(expect.any(Array))
    expect(poiOffset("fix-price")).toEqual(expect.any(Array))
    expect(poiOffset("gorzdrav")).not.toEqual(poiOffset("fix-price"))
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
    expect(map.setSky).toHaveBeenCalledWith({
      "sky-color": "#87ceeb",
      "sky-horizon-blend": 0.3,
      "horizon-color": "#f0f4ff",
      "horizon-fog-blend": 0.8,
      "fog-color": "#e8edf5",
      "fog-ground-blend": 0.5,
    })
    expect(window.matchMedia).toHaveBeenCalledWith("(prefers-reduced-motion: reduce)")
    await waitFor(
      () =>
        expect(map.flyTo).toHaveBeenCalledWith({
          center: [37.81478, 55.7144],
          zoom: 17,
          pitch: 45,
          bearing: 0,
          duration: 2500,
          essential: true,
        }),
      { timeout: 1500 }
    )
  })

  it.each([
    ["dawn", { sky: "#fbbf24", horizon: "#fca5a5", fog: "#fef3c7" }],
    ["morning", { sky: "#87ceeb", horizon: "#f0f4ff", fog: "#e8edf5" }],
    ["dusk", { sky: "#f59e0b", horizon: "#a78bfa", fog: "#fde68a" }],
  ] as const)("applies the exact %s sky palette", async (timePeriod, colors) => {
    const map = makeMap()

    render(
      <MapLibreMapComponent
        {...baseProps}
        mapRef={makeRef(map)}
        isDark={false}
        timePeriod={timePeriod}
      />
    )

    await waitFor(() =>
      expect(map.setSky).toHaveBeenCalledWith({
        "sky-color": colors.sky,
        "sky-horizon-blend": 0.3,
        "horizon-color": colors.horizon,
        "horizon-fog-blend": 0.8,
        "fog-color": colors.fog,
        "fog-ground-blend": 0.5,
      })
    )
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
      expect(map.jumpTo).toHaveBeenCalledWith({
        center: [37.8, 55.7],
        zoom: 17,
        pitch: 30,
        bearing: 90,
      })
    )
    expect(renderedMapProps.current.initialViewState).toEqual({
      longitude: 37.8,
      latitude: 55.7,
      zoom: 17,
      pitch: 30,
      bearing: 90,
    })
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
      await waitFor(() =>
        expect(map.jumpTo).toHaveBeenCalledWith({
          center: [37.81478, 55.7144],
          zoom: 17,
          pitch: 45,
          bearing: 0,
        })
      )
      expect(map.flyTo).not.toHaveBeenCalled()
    } finally {
      mm.mockRestore()
    }
  })

  it("jumps (no animation) on an explicitly constrained device", async () => {
    deviceState.lowPower = true
    const map = makeMap()

    render(<MapLibreMapComponent {...baseProps} mapRef={makeRef(map)} />)

    await waitFor(() =>
      expect(map.jumpTo).toHaveBeenCalledWith({
        center: [37.81478, 55.7144],
        zoom: 17,
        pitch: 45,
        bearing: 0,
      })
    )
    expect(map.flyTo).not.toHaveBeenCalled()
  })

  it("eases to the selected building when one is chosen", async () => {
    const map = makeMap()
    const ref = makeRef(map)
    const easeTo = (ref.current as unknown as { easeTo: ReturnType<typeof vi.fn> }).easeTo
    const { rerender } = render(<MapLibreMapComponent {...baseProps} mapRef={ref} />)
    expect(easeTo).not.toHaveBeenCalled()

    rerender(<MapLibreMapComponent {...baseProps} mapRef={ref} selectedBuilding="ГУК" />)
    await waitFor(() =>
      expect(easeTo).toHaveBeenCalledWith({
        center: [37.81165, 55.71405],
        duration: 600,
      })
    )
  })

  it("does not dereference an absent map while a building is selected", () => {
    expect(() =>
      render(<MapLibreMapComponent {...baseProps} selectedBuilding="ГУК" />)
    ).not.toThrow()
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
    deviceState.lowPower = true
    try {
      const { rerender } = render(
        <MapLibreMapComponent {...baseProps} mapRef={ref} isDark={false} />
      )
      await waitFor(() => expect(map.setSky).toHaveBeenCalled())
      map.setSky.mockClear()
      rerender(<MapLibreMapComponent {...baseProps} mapRef={ref} isDark={true} timePeriod="dawn" />)
      await waitFor(() =>
        expect(map.setSky).toHaveBeenCalledWith({
          "sky-color": "#0f172a",
          "sky-horizon-blend": 0.3,
          "horizon-color": "#1e293b",
          "horizon-fog-blend": 0.8,
          "fog-color": "#1e293b",
          "fog-ground-blend": 0.5,
        })
      )
      expect(map.resize).toHaveBeenCalledTimes(2)
      expect(map.jumpTo).toHaveBeenCalledTimes(1)
    } finally {
      requestFrame.mockRestore()
    }
  })

  it("updates the sky before a pending readiness frame executes", () => {
    const requestFrame = vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 1)
    const map = makeMap()
    const ref = makeRef(map)

    try {
      const { rerender } = render(
        <MapLibreMapComponent {...baseProps} mapRef={ref} isDark={false} />
      )
      expect(map.setSky).toHaveBeenCalledWith({
        "sky-color": "#87ceeb",
        "sky-horizon-blend": 0.3,
        "horizon-color": "#f0f4ff",
        "horizon-fog-blend": 0.8,
        "fog-color": "#e8edf5",
        "fog-ground-blend": 0.5,
      })

      map.setSky.mockClear()
      rerender(<MapLibreMapComponent {...baseProps} mapRef={ref} isDark timePeriod="night" />)
      expect(map.setSky).toHaveBeenCalledWith({
        "sky-color": "#0f172a",
        "sky-horizon-blend": 0.3,
        "horizon-color": "#1e293b",
        "horizon-fog-blend": 0.8,
        "fog-color": "#1e293b",
        "fog-ground-blend": 0.5,
      })
    } finally {
      requestFrame.mockRestore()
    }
  })

  it("recomputes the exact building set when the active category changes", () => {
    const { rerender } = render(<MapLibreMapComponent {...baseProps} />)
    expect(
      new Set(
        renderedMarkerProps.buildings.map((props) => (props.building as { letter: string }).letter)
      ).size
    ).toBe(9)

    renderedMarkerProps.buildings = []
    rerender(
      <MapLibreMapComponent
        {...baseProps}
        activeCategory={"sports" as typeof baseProps.activeCategory}
      />
    )

    expect(
      renderedMarkerProps.buildings.map((props) => (props.building as { letter: string }).letter)
    ).toEqual(["Б", "СК"])
  })

  it("recomputes localized building data when the resolved language changes", () => {
    const { rerender } = render(<MapLibreMapComponent {...baseProps} />)
    expect((latestBuilding("ГУК")?.building as { name: string }).name).toBe("Main Building (GUK)")

    translationState.resolvedLanguage = "ru"
    renderedMarkerProps.buildings = []
    rerender(<MapLibreMapComponent {...baseProps} />)

    expect((latestBuilding("ГУК")?.building as { name: string }).name).toBe(
      "Главный учебный корпус (ГУК)"
    )
  })

  it("counts repeated events per building and recomputes counts after updates", () => {
    const firstEvent = {
      id: "event-1",
      buildingId: "ГУК",
      geoCoords: [55.71405, 37.81165],
    } as never
    const secondEvent = {
      id: "event-2",
      buildingId: "ГУК",
      geoCoords: [55.71405, 37.81165],
    } as never
    const { rerender } = render(<MapLibreMapComponent {...baseProps} mapEvents={[firstEvent]} />)
    expect(latestBuilding("ГУК")?.eventCount).toBe(1)
    expect(latestBuilding("ПА")?.eventCount).toBe(0)

    renderedMarkerProps.buildings = []
    rerender(<MapLibreMapComponent {...baseProps} mapEvents={[firstEvent, secondEvent]} />)

    expect(latestBuilding("ГУК")?.eventCount).toBe(2)
    expect(latestBuilding("ПА")?.eventCount).toBe(0)
  })

  it("refreshes a live projection when async map events arrive", async () => {
    const requestFrame = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback) => {
        callback(0)
        return 1
      })
    const map = makeMap()
    const ref = makeRef(map)
    const event = {
      id: "late-event",
      buildingId: "ГУК",
      geoCoords: [45.6, 12.3],
    } as never

    try {
      const { rerender } = render(
        <MapLibreMapComponent {...baseProps} mapRef={ref} mapEvents={[]} />
      )
      await waitFor(() => expect(map.project).toHaveBeenCalled())
      map.project.mockClear()
      renderedMarkerProps.events = []

      rerender(<MapLibreMapComponent {...baseProps} mapRef={ref} mapEvents={[event]} />)
      await waitFor(() => expect(map.project).toHaveBeenCalledWith([12.3, 45.6]))
      expect(latestEvent("late-event")?.offset).toEqual(expect.any(Array))
    } finally {
      requestFrame.mockRestore()
    }
  })

  it("projects canonical building, POI, and event coordinates under stable collision ids", async () => {
    const map = makeMap()
    const event = {
      id: "projection-event",
      buildingId: "ГУК",
      geoCoords: [45.6, 12.3],
    } as never

    render(<MapLibreMapComponent {...baseProps} mapRef={makeRef(map)} mapEvents={[event]} />)

    await waitFor(() => expect(map.project).toHaveBeenCalledWith([37.81165, 55.71405]))
    expect(map.project).toHaveBeenCalledWith([37.8164, 55.7126])
    expect(map.project).toHaveBeenCalledWith([12.3, 45.6])
    await waitFor(() => expect(latestBuilding("ГУК")?.offset).toEqual(expect.any(Array)))
    expect(latestPoi("gorzdrav")?.offset).toEqual(expect.any(Array))
    expect(latestEvent("projection-event")?.offset).toEqual(expect.any(Array))
  })

  it("uses MapLibre projected screen points rather than geographic fallback offsets", async () => {
    const map = makeMap()
    map.project.mockReturnValue({ x: 400, y: 300 })
    const event = {
      id: "screen-collision",
      buildingId: "ГУК",
      geoCoords: [0, 0],
    } as never

    render(<MapLibreMapComponent {...baseProps} mapRef={makeRef(map)} mapEvents={[event]} />)

    await waitFor(() => {
      expect(latestEvent("screen-collision")?.offset).toEqual(expect.any(Array))
      expect(latestEvent("screen-collision")?.offset).not.toEqual([0, 0])
    })
  })

  it("keeps exactly one marker popup open and closes it on the map surface", () => {
    const onDeselectBuilding = vi.fn()
    render(
      <MapLibreMapComponent
        {...baseProps}
        onDeselectBuilding={onDeselectBuilding}
        mapRef={makeRef(makeMap())}
        weatherCondition="rain"
        mapEvents={[{ id: "event-1", buildingId: "ГУК", geoCoords: [55.71405, 37.81165] } as never]}
      />
    )

    expect(latestBuilding("ГУК")?.isPopupOpen).toBe(false)
    expect(latestPoi("gorzdrav")?.isPopupOpen).toBe(false)
    expect(latestEvent("event-1")?.isPopupOpen).toBe(false)
    expect(renderedOverlayProps.weather.length).toBeGreaterThan(0)
    expect(
      renderedOverlayProps.weather.every(
        (props) => props.condition === "rain" && props.isDark === false
      )
    ).toBe(true)

    fireEvent.click(screen.getByTestId("building-open-ГУК"))
    expect(latestBuilding("ГУК")?.isPopupOpen).toBe(true)
    expect(latestBuilding("ПА")?.isPopupOpen).toBe(false)
    expect(onDeselectBuilding).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId("map-click"))
    expect(onDeselectBuilding).toHaveBeenCalledTimes(1)
    expect(latestBuilding("ГУК")?.isPopupOpen).toBe(false)

    fireEvent.click(screen.getByTestId("building-open-ГУК"))
    fireEvent.click(screen.getByTestId("building-close-ГУК"))
    expect(latestBuilding("ГУК")?.isPopupOpen).toBe(false)

    fireEvent.click(screen.getAllByTestId("poi-open")[0]!)
    expect(onDeselectBuilding).toHaveBeenCalledTimes(2)
    expect(latestPoi("metro-vykhino")?.isPopupOpen).toBe(true)
    expect(latestBuilding("ГУК")?.isPopupOpen).toBe(false)
    fireEvent.click(screen.getAllByTestId("poi-close")[0]!)
    expect(latestPoi("metro-vykhino")?.isPopupOpen).toBe(false)

    fireEvent.click(screen.getByTestId("event-open"))
    expect(onDeselectBuilding).toHaveBeenCalledTimes(3)
    expect(latestEvent("event-1")?.isPopupOpen).toBe(true)
    expect(latestPoi("metro-vykhino")?.isPopupOpen).toBe(false)
    fireEvent.click(screen.getByTestId("event-close"))
    expect(latestEvent("event-1")?.isPopupOpen).toBe(false)
  })

  it("forwards selection and highlight state only to the matching building", () => {
    const onSelectBuilding = vi.fn()
    render(
      <MapLibreMapComponent
        {...baseProps}
        onSelectBuilding={onSelectBuilding}
        selectedBuilding="ГУК"
        highlightedBuilding="ПА"
      />
    )

    expect(latestBuilding("ГУК")).toEqual(
      expect.objectContaining({
        index: 0,
        isSelected: true,
        isHighlighted: false,
        onClick: onSelectBuilding,
      })
    )
    expect(latestBuilding("ПА")).toEqual(
      expect.objectContaining({ isSelected: false, isHighlighted: true })
    )
    expect(latestBuilding("ЛК")).toEqual(
      expect.objectContaining({ isSelected: false, isHighlighted: false })
    )
  })

  it("renders weather only when supplied and forwards the exact theme", () => {
    const { rerender } = render(<MapLibreMapComponent {...baseProps} />)
    expect(renderedOverlayProps.weather).toHaveLength(0)

    rerender(<MapLibreMapComponent {...baseProps} weatherCondition="snow" isDark />)
    expect(renderedOverlayProps.weather).toEqual([{ condition: "snow", isDark: true }])
  })

  it("latches URL synchronization after user input and emits the complete camera", () => {
    const onMapMoveEnd = vi.fn()
    render(
      <MapLibreMapComponent
        {...baseProps}
        onMapMoveEnd={onMapMoveEnd}
        mapRef={makeRef(makeMap())}
      />
    )

    currentMoveEndHandler()({})
    expect(onMapMoveEnd).not.toHaveBeenCalled()
    currentMoveEndHandler()({ originalEvent: { type: "mouse" } })
    currentMoveEndHandler()({})

    expect(onMapMoveEnd).toHaveBeenCalledTimes(2)
    expect(onMapMoveEnd).toHaveBeenNthCalledWith(1, {
      zoom: 16,
      latitude: 55.7,
      longitude: 37.8,
      pitch: 45,
      bearing: 0,
    })
    expect(onMapMoveEnd).toHaveBeenNthCalledWith(2, {
      zoom: 16,
      latitude: 55.7,
      longitude: 37.8,
      pitch: 45,
      bearing: 0,
    })
  })

  it("uses the latest URL synchronization callback after a rerender", () => {
    const firstCallback = vi.fn()
    const nextCallback = vi.fn()
    const ref = makeRef(makeMap())
    const { rerender } = render(
      <MapLibreMapComponent {...baseProps} onMapMoveEnd={firstCallback} mapRef={ref} />
    )

    rerender(<MapLibreMapComponent {...baseProps} onMapMoveEnd={nextCallback} mapRef={ref} />)
    currentMoveEndHandler()({ originalEvent: { type: "mouse" } })

    expect(firstCallback).not.toHaveBeenCalled()
    expect(nextCallback).toHaveBeenCalledWith({
      zoom: 16,
      latitude: 55.7,
      longitude: 37.8,
      pitch: 45,
      bearing: 0,
    })
  })

  it("keeps move-end safe when the map or callback is absent", () => {
    const emptyRef = { current: null } as React.MutableRefObject<MapRef | null>
    const { rerender } = render(<MapLibreMapComponent {...baseProps} />)
    currentMoveEndHandler()({ originalEvent: { type: "mouse" } })

    rerender(<MapLibreMapComponent {...baseProps} mapRef={emptyRef} />)
    currentMoveEndHandler()({ originalEvent: { type: "mouse" } })

    rerender(<MapLibreMapComponent {...baseProps} mapRef={makeRef(makeMap())} />)
    currentMoveEndHandler()({ originalEvent: { type: "mouse" } })
  })

  it("uses the base language and skips an unknown selected building", () => {
    translationState.resolvedLanguage = undefined
    translationState.language = "ru"
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

    expect((latestBuilding("ГУК")?.building as { name: string }).name).toBe(
      "Главный учебный корпус (ГУК)"
    )
    expect(easeTo).not.toHaveBeenCalled()
  })

  it("stops a pending map-readiness poll after unmount", () => {
    let pendingFrame: FrameRequestCallback | undefined
    let frameId = 0
    const requestAnimationFrame = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback) => {
        pendingFrame = callback
        frameId += 1
        return frameId
      })
    const cancelAnimationFrame = vi
      .spyOn(window, "cancelAnimationFrame")
      .mockImplementation(() => undefined)

    try {
      const map = makeMap()
      map.loaded.mockReturnValue(false)
      const { unmount } = render(<MapLibreMapComponent {...baseProps} mapRef={makeRef(map)} />)
      pendingFrame?.(0)
      expect(requestAnimationFrame).toHaveBeenCalledTimes(2)
      expect(map.resize).not.toHaveBeenCalled()
      const loadedCallsBeforeUnmount = map.loaded.mock.calls.length
      unmount()
      pendingFrame?.(0)
      expect(map.loaded).toHaveBeenCalledTimes(loadedCallsBeforeUnmount)
      expect(cancelAnimationFrame).toHaveBeenCalledWith(2)
    } finally {
      requestAnimationFrame.mockRestore()
      cancelAnimationFrame.mockRestore()
    }
  })

  it("keeps polling safely while the forwarded map ref is still null", () => {
    const pendingFrames: FrameRequestCallback[] = []
    const requestAnimationFrame = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback) => {
        pendingFrames.push(callback)
        return pendingFrames.length
      })
    const emptyRef = { current: null } as React.MutableRefObject<MapRef | null>

    try {
      render(<MapLibreMapComponent {...baseProps} mapRef={emptyRef} />)
      expect(() => pendingFrames[0]?.(0)).not.toThrow()
      expect(requestAnimationFrame).toHaveBeenCalledTimes(2)
    } finally {
      requestAnimationFrame.mockRestore()
    }
  })

  it("keeps polling safely before an optional map ref is supplied", () => {
    const pendingFrames: FrameRequestCallback[] = []
    const requestAnimationFrame = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback) => {
        pendingFrames.push(callback)
        return pendingFrames.length
      })

    try {
      render(<MapLibreMapComponent {...baseProps} />)
      pendingFrames[0]?.(0)
      expect(requestAnimationFrame).toHaveBeenCalledTimes(2)
    } finally {
      requestAnimationFrame.mockRestore()
    }
  })

  it("projects immediately from a loaded map and repeats for a replacement ref", () => {
    const requestAnimationFrame = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation(() => 1)
    const firstMap = makeMap()
    const nextMap = makeMap()

    try {
      const { rerender } = render(
        <MapLibreMapComponent {...baseProps} mapRef={makeRef(firstMap)} />
      )
      expect(firstMap.project).toHaveBeenCalledWith([37.81165, 55.71405])

      rerender(<MapLibreMapComponent {...baseProps} mapRef={makeRef(nextMap)} />)
      expect(nextMap.project).toHaveBeenCalledWith([37.81165, 55.71405])
    } finally {
      requestAnimationFrame.mockRestore()
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
    const clearTimeout = vi.spyOn(globalThis, "clearTimeout")

    try {
      const { unmount } = render(<MapLibreMapComponent {...baseProps} mapRef={makeRef(map)} />)
      pendingFrame?.(0)
      expect(map.resize).toHaveBeenCalled()
      expect(introCallback).toBeDefined()
      unmount()
      expect(clearTimeout).toHaveBeenCalledWith(99)
      introCallback?.()
      expect(map.flyTo).not.toHaveBeenCalled()
    } finally {
      requestAnimationFrame.mockRestore()
      setTimeout.mockRestore()
      clearTimeout.mockRestore()
    }
  })

  it("does not clear a nonexistent intro timeout after an immediate reduced-motion jump", () => {
    const map = makeMap()
    const requestAnimationFrame = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback) => {
        callback(0)
        return 1
      })
    const clearTimeout = vi.spyOn(globalThis, "clearTimeout")
    deviceState.lowPower = true

    try {
      const { unmount } = render(<MapLibreMapComponent {...baseProps} mapRef={makeRef(map)} />)
      expect(map.jumpTo).toHaveBeenCalledTimes(1)
      unmount()
      expect(clearTimeout).not.toHaveBeenCalledWith(null)
    } finally {
      requestAnimationFrame.mockRestore()
      clearTimeout.mockRestore()
    }
  })
})
