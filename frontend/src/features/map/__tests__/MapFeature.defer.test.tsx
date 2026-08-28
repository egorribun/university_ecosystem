import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { Suspense, type ComponentType } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", resolvedLanguage: "en", changeLanguage: () => Promise.resolve() },
  }),
  withTranslation: () => (Component: ComponentType) => Component,
  Trans: ({ children }: { children?: React.ReactNode }) => children,
}))

vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))
vi.mock("@/hooks/useURLState", () => ({
  useURLState: () => ({ params: {}, setParam: vi.fn(), setParams: vi.fn() }),
}))
vi.mock("@/hooks/useTimeOfDay", () => ({ useTimeOfDay: () => "afternoon" }))
vi.mock("@/hooks/useSeason", () => ({ useSeason: () => "spring" }))
vi.mock("@/hooks/useNextLesson", () => ({ useNextLesson: () => null }))
vi.mock("@/hooks/useScheduleData", () => ({ useScheduleData: () => ({ todayLessons: [] }) }))
vi.mock("@/hooks/useMapEvents", () => ({ useMapEvents: () => ({ events: [], isLoading: false }) }))
vi.mock("@/hooks/useMapWeather", () => ({ useMapWeather: () => ({ data: undefined }) }))
vi.mock("@/hooks/useMapKeyboardShortcuts", () => ({ useMapKeyboardShortcuts: () => undefined }))

vi.mock("@/components/map/MapBackdrop", () => ({ MapBackdrop: () => null }))
vi.mock("@/components/map/MapHeader", () => ({ MapHeader: () => null }))
vi.mock("@/components/map/MapWeatherBadge", () => ({ MapWeatherBadge: () => null }))
vi.mock("@/components/map/MapCategoryFilter", () => ({ MapCategoryFilter: () => null }))
vi.mock("@/components/map/MapSearchBar", () => ({ MapSearchBar: () => null }))
vi.mock("@/components/map/MapShortcutsOverlay", () => ({ MapShortcutsOverlay: () => null }))
vi.mock("@/components/error", () => ({
  WidgetErrorBoundary: ({ children }: { children: React.ReactNode }) => children,
}))
vi.mock("@/components/motion/FadeSection", () => ({
  default: ({ children }: { children: React.ReactNode }) => children,
}))

const mapLoader = vi.hoisted(() =>
  vi.fn(() => Promise.resolve({ default: () => <div data-testid="map-component" /> }))
)
vi.mock("@/features/map/loadMapLibre", () => ({ loadMapLibre: mapLoader }))

import { MapFeature } from "@/features/map/MapFeature"

describe("MapFeature deferred MapLibre loading", () => {
  beforeEach(() => {
    mapLoader.mockClear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it("keeps MapLibre unloaded while the accessible placeholder is idle", async () => {
    render(
      <Suspense fallback={null}>
        <MapFeature />
      </Suspense>
    )

    expect(screen.getByRole("button", { name: "campusMap.interactiveHint" })).toBeInTheDocument()
    await act(async () => {
      await Promise.resolve()
    })
    expect(mapLoader).not.toHaveBeenCalled()
  })

  it("loads MapLibre immediately after explicit pointer intent", async () => {
    render(
      <Suspense fallback={null}>
        <MapFeature />
      </Suspense>
    )

    fireEvent.pointerDown(screen.getByRole("button", { name: "campusMap.interactiveHint" }))

    await waitFor(() => expect(mapLoader).toHaveBeenCalledTimes(1))
    expect(await screen.findByTestId("map-component")).toBeInTheDocument()
  })

  it("restores focus to the map region after pointer activation replaces the placeholder", async () => {
    render(
      <Suspense fallback={null}>
        <MapFeature />
      </Suspense>
    )

    fireEvent.pointerDown(screen.getByRole("button", { name: "campusMap.interactiveHint" }))

    expect(await screen.findByTestId("map-component")).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "campusMap.ariaLabel" })).toHaveFocus()
  })

  it("activates the map from a direct click and restores focus", async () => {
    render(
      <Suspense fallback={null}>
        <MapFeature />
      </Suspense>
    )

    fireEvent.click(screen.getByRole("button", { name: "campusMap.interactiveHint" }))

    expect(await screen.findByTestId("map-component")).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "campusMap.ariaLabel" })).toHaveFocus()
  })

  it("activates from keyboard focus on the accessible placeholder", async () => {
    render(
      <Suspense fallback={null}>
        <MapFeature />
      </Suspense>
    )

    const placeholder = screen.getByRole("button", { name: "campusMap.interactiveHint" })
    placeholder.focus()

    expect(await screen.findByTestId("map-component")).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "campusMap.ariaLabel" })).toHaveFocus()
  })

  it("does not auto-load MapLibre when the placeholder reaches the viewport", async () => {
    render(
      <Suspense fallback={null}>
        <MapFeature />
      </Suspense>
    )

    // MapLibre is a large WebGL dependency. Viewport visibility alone must
    // not execute it: users activate the map through the accessible button,
    // while route-level intent preloading remains available in _auth/map.
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.getByRole("button", { name: "campusMap.interactiveHint" })).toBeInTheDocument()
    expect(mapLoader).not.toHaveBeenCalled()
  })
})
