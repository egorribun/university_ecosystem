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

import { __testing as mapTesting, MapFeature } from "@/features/map/MapFeature"

type IntersectionCallback = (entries: IntersectionObserverEntry[]) => void

class ControlledIntersectionObserver {
  static callback: IntersectionCallback | undefined
  static disconnect = vi.fn()

  constructor(callback: IntersectionObserverCallback) {
    ControlledIntersectionObserver.callback = (entries) =>
      callback(entries, this as unknown as IntersectionObserver)
  }

  observe = vi.fn()
  disconnect = ControlledIntersectionObserver.disconnect
}

const originalIntersectionObserver = window.IntersectionObserver

describe("MapFeature deferred MapLibre loading", () => {
  beforeEach(() => {
    mapLoader.mockClear()
    ControlledIntersectionObserver.callback = undefined
    ControlledIntersectionObserver.disconnect.mockClear()
  })

  afterEach(() => {
    window.IntersectionObserver = originalIntersectionObserver
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

  it("activates from keyboard focus on the accessible placeholder", async () => {
    render(
      <Suspense fallback={null}>
        <MapFeature />
      </Suspense>
    )

    fireEvent.focus(screen.getByRole("button", { name: "campusMap.interactiveHint" }))

    expect(await screen.findByTestId("map-component")).toBeInTheDocument()
  })

  it("loads MapLibre from an idle callback once the viewport becomes visible", async () => {
    window.IntersectionObserver =
      ControlledIntersectionObserver as unknown as typeof IntersectionObserver
    const idleCallbacks: IdleRequestCallback[] = []
    const requestIdle = vi.fn((callback: IdleRequestCallback) => {
      idleCallbacks.push(callback)
      return 17
    })
    Object.defineProperty(window, "requestIdleCallback", {
      configurable: true,
      value: requestIdle,
    })

    render(
      <Suspense fallback={null}>
        <MapFeature />
      </Suspense>
    )

    expect(mapLoader).not.toHaveBeenCalled()
    act(() => {
      ControlledIntersectionObserver.callback?.([
        { isIntersecting: true } as IntersectionObserverEntry,
      ])
    })

    expect(requestIdle).toHaveBeenCalledWith(expect.any(Function), { timeout: 4000 })
    expect(mapLoader).not.toHaveBeenCalled()

    await act(async () => {
      idleCallbacks[0]?.({ didTimeout: false, timeRemaining: () => 50 })
      await Promise.resolve()
    })
    expect(await screen.findByTestId("map-component")).toBeInTheDocument()
  })

  it("waits for visibility before scheduling an idle map load", async () => {
    window.IntersectionObserver =
      ControlledIntersectionObserver as unknown as typeof IntersectionObserver
    const idleCallbacks: IdleRequestCallback[] = []
    const requestIdle = vi.fn((callback: IdleRequestCallback) => {
      idleCallbacks.push(callback)
      return 23
    })
    Object.defineProperty(window, "requestIdleCallback", {
      configurable: true,
      value: requestIdle,
    })
    const visibility = vi.spyOn(document, "visibilityState", "get")
    visibility.mockReturnValue("hidden")

    render(
      <Suspense fallback={null}>
        <MapFeature />
      </Suspense>
    )
    act(() => {
      ControlledIntersectionObserver.callback?.([
        { isIntersecting: true } as IntersectionObserverEntry,
      ])
    })
    expect(requestIdle).not.toHaveBeenCalled()

    visibility.mockReturnValue("visible")
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    expect(requestIdle).toHaveBeenCalledTimes(1)

    await act(async () => {
      idleCallbacks[0]?.({ didTimeout: true, timeRemaining: () => 0 })
      await Promise.resolve()
    })
    expect(await screen.findByTestId("map-component")).toBeInTheDocument()
  })

  it("cancels a pending native idle load when the map unmounts", () => {
    window.IntersectionObserver =
      ControlledIntersectionObserver as unknown as typeof IntersectionObserver
    const cancelIdle = vi.fn()
    Object.defineProperty(window, "requestIdleCallback", {
      configurable: true,
      value: vi.fn(() => 31),
    })
    Object.defineProperty(window, "cancelIdleCallback", {
      configurable: true,
      value: cancelIdle,
    })

    const { unmount } = render(
      <Suspense fallback={null}>
        <MapFeature />
      </Suspense>
    )
    act(() => {
      ControlledIntersectionObserver.callback?.([
        { isIntersecting: true } as IntersectionObserverEntry,
      ])
    })
    unmount()

    expect(cancelIdle).toHaveBeenCalledWith(31)
  })

  it("ignores an idle callback that fires after the map unmounts", () => {
    window.IntersectionObserver =
      ControlledIntersectionObserver as unknown as typeof IntersectionObserver
    let idleCallback: IdleRequestCallback | undefined
    Object.defineProperty(window, "requestIdleCallback", {
      configurable: true,
      value: vi.fn((callback: IdleRequestCallback) => {
        idleCallback = callback
        return 37
      }),
    })

    const { unmount } = render(
      <Suspense fallback={null}>
        <MapFeature />
      </Suspense>
    )
    act(() => {
      ControlledIntersectionObserver.callback?.([
        { isIntersecting: true } as IntersectionObserverEntry,
      ])
    })
    unmount()

    act(() => {
      idleCallback?.({ didTimeout: false, timeRemaining: () => 50 })
    })
    expect(mapLoader).not.toHaveBeenCalled()
  })

  it("provides an IdleDeadline-compatible timeout fallback", () => {
    vi.useFakeTimers()
    Reflect.deleteProperty(window, "requestIdleCallback")
    const callback = vi.fn((deadline: IdleDeadline) => {
      expect(deadline.didTimeout).toBe(true)
      expect(deadline.timeRemaining()).toBe(0)
    })

    mapTesting.scheduleMapIdleCallback(callback, 4000)
    vi.advanceTimersByTime(4000)

    expect(callback).toHaveBeenCalledTimes(1)
  })

  it("cancels the timeout fallback and ignores a late idle callback", () => {
    window.IntersectionObserver =
      ControlledIntersectionObserver as unknown as typeof IntersectionObserver
    vi.useFakeTimers()
    Reflect.deleteProperty(window, "requestIdleCallback")
    Reflect.deleteProperty(window, "cancelIdleCallback")
    const { unmount } = render(
      <Suspense fallback={null}>
        <MapFeature />
      </Suspense>
    )
    act(() => {
      ControlledIntersectionObserver.callback?.([
        { isIntersecting: true } as IntersectionObserverEntry,
      ])
    })
    unmount()
    vi.runOnlyPendingTimers()

    expect(mapLoader).not.toHaveBeenCalled()
  })

  it("uses the timeout fallback when IntersectionObserver is unavailable", async () => {
    window.IntersectionObserver = undefined as unknown as typeof IntersectionObserver
    vi.useFakeTimers()

    render(
      <Suspense fallback={null}>
        <MapFeature />
      </Suspense>
    )
    await act(async () => {
      await Promise.resolve()
    })
    await act(async () => {
      vi.advanceTimersByTime(4000)
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(screen.getByTestId("map-component")).toBeInTheDocument()
  })
})
