import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { useEffect, type ComponentType, type ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  loadMapLibre: vi.fn<() => Promise<{ default: ComponentType }>>(),
  captureException: vi.fn(),
  logError: vi.fn(),
  logWarning: vi.fn(),
  mounted: vi.fn(),
  unmounted: vi.fn(),
}))

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", resolvedLanguage: "en", changeLanguage: () => Promise.resolve() },
  }),
  withTranslation: () => (Component: ComponentType) => Component,
  Trans: ({ children }: { children?: ReactNode }) => children,
}))

// Keep actual error boundaries; mock only their reporting sinks.
vi.mock("@sentry/react", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@sentry/react")>()),
  captureException: mocks.captureException,
}))

vi.mock("@/app/logger", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/app/logger")>()),
  logError: mocks.logError,
  logWarning: mocks.logWarning,
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
vi.mock("@/components/motion/FadeSection", () => ({
  default: ({ children }: { children: ReactNode }) => children,
}))

vi.mock("@/features/map/loadMapLibre", () => ({
  loadMapLibre: mocks.loadMapLibre,
}))

// Import once: resetting modules would hide the cached rejected lazy identity.
import { MapFeature } from "@/features/map/MapFeature"

function createDeferred<T>() {
  let controls:
    | {
        resolve: (value: T | PromiseLike<T>) => void
        reject: (reason: unknown) => void
      }
    | undefined

  const promise = new Promise<T>((resolve, reject) => {
    controls = { resolve, reject }
  })

  if (!controls) {
    throw new Error("Deferred promise controls were not initialized")
  }

  return { promise, ...controls }
}

function LoadedMap() {
  useEffect(() => {
    mocks.mounted()
    return () => {
      mocks.unmounted()
    }
  }, [])

  return <div data-testid="map-component" />
}

describe("MapFeature lazy-load recovery", () => {
  it("retries after reopening and keeps the loaded map stable", async () => {
    const failure = new Error("transient map load failure")
    const firstAttempt = createDeferred<{ default: ComponentType }>()
    const secondAttempt = createDeferred<{ default: ComponentType }>()
    const caughtError = vi.fn()

    mocks.loadMapLibre
      .mockImplementationOnce(() => firstAttempt.promise)
      .mockImplementationOnce(() => secondAttempt.promise)

    // React 19 reports caught render errors here. Check identity and then
    // cardinality at the assertions, without changing strict-console policy.
    const onCaughtError = (error: unknown) => {
      expect(error).toBe(failure)
      caughtError(error)
    }

    const first = render(<MapFeature />, { onCaughtError })

    const activation = screen.getByRole("button", { name: "campusMap.interactiveHint" })
    expect(activation).toBeInTheDocument()
    expect(mocks.loadMapLibre).not.toHaveBeenCalled()

    fireEvent.click(activation)

    expect(await screen.findByText("campusMap.loading")).toBeInTheDocument()
    expect(mocks.loadMapLibre).toHaveBeenCalledTimes(1)

    await act(async () => {
      firstAttempt.reject(failure)
    })

    expect(await screen.findByText("campusMap.loadError")).toBeInTheDocument()
    expect(caughtError).toHaveBeenCalledExactlyOnceWith(failure)
    expect(mocks.captureException).toHaveBeenCalledExactlyOnceWith(
      failure,
      expect.objectContaining({
        tags: { errorBoundary: "widget", widget: "MapLibreGL" },
        level: "info",
      })
    )
    expect(mocks.mounted).not.toHaveBeenCalled()
    expect(mocks.unmounted).not.toHaveBeenCalled()

    first.rerender(<MapFeature />)

    expect(screen.getByText("campusMap.loadError")).toBeInTheDocument()
    expect(mocks.loadMapLibre).toHaveBeenCalledTimes(1)
    expect(caughtError).toHaveBeenCalledTimes(1)

    first.unmount()

    const second = render(<MapFeature />, { onCaughtError })

    const reactivation = screen.getByRole("button", { name: "campusMap.interactiveHint" })
    expect(reactivation).toBeInTheDocument()
    expect(screen.queryByText("campusMap.loadError")).not.toBeInTheDocument()

    await act(async () => {
      await Promise.resolve()
    })
    expect(mocks.loadMapLibre).toHaveBeenCalledTimes(1)

    fireEvent.click(reactivation)

    await waitFor(() => expect(mocks.loadMapLibre).toHaveBeenCalledTimes(2))
    expect(screen.getByText("campusMap.loading")).toBeInTheDocument()

    await act(async () => {
      secondAttempt.resolve({ default: LoadedMap })
    })

    const loadedMap = await screen.findByTestId("map-component")
    expect(screen.queryByText("campusMap.loadError")).not.toBeInTheDocument()
    expect(screen.queryByText("campusMap.loading")).not.toBeInTheDocument()
    expect(mocks.mounted).toHaveBeenCalledTimes(1)
    expect(mocks.unmounted).not.toHaveBeenCalled()

    second.rerender(<MapFeature />)

    expect(screen.getByTestId("map-component")).toBe(loadedMap)
    expect(mocks.loadMapLibre).toHaveBeenCalledTimes(2)
    expect(mocks.mounted).toHaveBeenCalledTimes(1)
    expect(mocks.unmounted).not.toHaveBeenCalled()
    expect(caughtError).toHaveBeenCalledTimes(1)
    expect(mocks.captureException).toHaveBeenCalledTimes(1)

    second.unmount()

    expect(mocks.unmounted).toHaveBeenCalledTimes(1)
    expect(screen.queryByTestId("map-component")).not.toBeInTheDocument()
    expect(mocks.loadMapLibre).toHaveBeenCalledTimes(2)
  })
})
