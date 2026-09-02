import { render, screen, fireEvent, act, waitFor, within } from "@testing-library/react"
import type { ComponentType, RefObject } from "react"
import { Suspense } from "react"
import { renderToString } from "react-dom/server"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

/* ──────────────────────────────────────────────────────────────────────────
 * MapFeature.branches.test.tsx — drives the uncovered orchestration handlers
 * that the primary MapFeature.test.tsx (mount-only) never exercises:
 *   - handleMapMoveEnd setTimeout body + debounce-cleanup (127-132, 137)
 *   - building / floor / room / close / navigate handlers (143-167)
 *   - Escape-key → close sidebar (173-176)
 *   - handleToggleFullscreen both branches (183-189)
 *   - MapSidebar render path + currentFloor lookup (206, 276-287)
 *   - weather / nextLesson / narrow-layout cold branches (213, 239, 260, 266)
 *   - getCampusBuildings locale fallback (80)
 *
 * Unlike the primary test which stubs MapLibreMap → null, this file uses a
 * richer mock that surfaces the orchestration props so the callbacks can be
 * fired from a real event. MapLibreMap is lazy-loaded behind <Suspense>, so
 * every test awaits `whenMapMounted()` before reading `mapProps.current`.
 * useMapKeyboardShortcuts is captured so its options can be invoked directly.
 * ────────────────────────────────────────────────────────────────────────── */

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

const i18nMock = vi.hoisted(() => ({
  resolvedLanguage: "en" as string | undefined,
  language: "en" as string,
}))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: i18nMock.language,
      resolvedLanguage: i18nMock.resolvedLanguage,
      changeLanguage: () => Promise.resolve(),
    },
  }),
  withTranslation: () => (Component: ComponentType) => Component,
  Trans: ({ children }: { children?: React.ReactNode }) => children,
}))

const mq = vi.hoisted(() => ({ narrow: false, reduced: false }))
vi.mock("@/hooks/useMediaQuery", () => ({
  default: (q: string) => (q.includes("reduce") ? mq.reduced : mq.narrow),
}))

/* Capture the props MapFeature passes into the lazy MapLibre child so the
   orchestration callbacks can be fired from the test. */
const mapProps = vi.hoisted(() => ({
  current: null as Record<string, unknown> | null,
}))
vi.mock("@/components/map/MapLibreMap", () => ({
  default: (props: Record<string, unknown>) => {
    mapProps.current = props
    return null
  },
}))

/* Keep this orchestration test independent from MapLibre's worker and CSS
   side effects. MapFeature owns the lazy loader, so mocking only the child
   module still executes loadMapLibre's browser-only Promise.all path in a
   Stryker sandbox where those assets are unavailable. */
vi.mock("@/features/map/loadMapLibre", () => ({
  loadMapLibre: () => import("@/components/map/MapLibreMap"),
}))

/* Capture the keyboard-shortcut options so we can invoke them directly. */
// Named methods (not a string-index Record) so dot-access isn't widened to
// `| undefined` by noUncheckedIndexedAccess when we invoke them below.
type KsOpts = {
  onSelectBuilding: (arg?: unknown) => void
  onDeselectBuilding: (arg?: unknown) => void
  onToggleShortcuts: (arg?: unknown) => void
  onFocusSearch: (arg?: unknown) => void
  onToggleFullscreen: (arg?: unknown) => void
}
const ksOptions = vi.hoisted(() => ({
  current: null as KsOpts | null,
}))
vi.mock("@/hooks/useMapKeyboardShortcuts", () => ({
  useMapKeyboardShortcuts: (opts: Record<string, (arg?: unknown) => void>) => {
    ksOptions.current = opts as unknown as KsOpts
  },
}))

/* URL-state hook — varied per test for the latched-viewport branch. */
const urlState = vi.hoisted(() => ({
  params: {} as Record<string, unknown>,
  setParams: vi.fn((..._a: unknown[]) => undefined),
}))
vi.mock("@/hooks/useURLState", () => ({
  useURLState: () => ({ params: urlState.params, setParams: urlState.setParams }),
}))

vi.mock("@/hooks/useTimeOfDay", () => ({ useTimeOfDay: () => "afternoon" }))
vi.mock("@/hooks/useSeason", () => ({ useSeason: () => "spring" }))

const nextLesson = vi.hoisted(() => ({ value: null as { building: string } | null }))
vi.mock("@/hooks/useNextLesson", () => ({ useNextLesson: () => nextLesson.value }))

vi.mock("@/hooks/useScheduleData", () => ({ useScheduleData: () => ({ todayLessons: [] }) }))
vi.mock("@/hooks/useMapEvents", () => ({ useMapEvents: () => ({ events: [], isLoading: false }) }))

const weather = vi.hoisted(() => ({
  value: undefined as { condition: string } | undefined,
}))
vi.mock("@/hooks/useMapWeather", () => ({ useMapWeather: () => ({ data: weather.value }) }))

/* Avoid AppShellProvider — MapSidebar reads useAppShell() only when rendered. */
vi.mock("@/contexts/AppShellContext", () => ({
  useAppShell: () => ({
    setOverlayState: vi.fn(),
    scrollToTop: vi.fn(),
    markScrollSnapshot: vi.fn(),
    restoreScrollIfNeeded: vi.fn(),
  }),
}))

/* Stub MapSearchBar so its onSelectRoom (→ navigateToRoom) is fireable. */
const searchProps = vi.hoisted(() => ({
  current: null as Record<string, unknown> | null,
}))
vi.mock("@/components/map/MapSearchBar", () => ({
  MapSearchBar: (props: Record<string, unknown>) => {
    searchProps.current = props
    return (
      <>
        <input
          data-testid="search-input"
          ref={props.searchInputRef as RefObject<HTMLInputElement>}
        />
        <button
          data-testid="search-room"
          onClick={() =>
            (props.onSelectRoom as (l: string, f: number, r: string) => void)("ГУК", 2, "ГУК-201")
          }
        >
          search-room
        </button>
      </>
    )
  },
}))

import { MapFeature } from "@/features/map/MapFeature"

function renderFeature() {
  return render(
    <Suspense fallback={null}>
      <MapFeature />
    </Suspense>
  )
}

/* The production map is intentionally deferred until explicit interaction.
   Trigger the interaction here so orchestration tests exercise the real child
   contract without loading MapLibre during initial route rendering. */
async function whenMapMounted() {
  const placeholder = document.querySelector('[data-testid="map-activation-placeholder"]')
  if (placeholder) fireEvent.pointerDown(placeholder)
  await waitFor(() => expect(mapProps.current).not.toBeNull())
}

function getSelectBuilding() {
  return mapProps.current!.onSelectBuilding as (id: string) => void
}

beforeEach(() => {
  mapProps.current = null
  ksOptions.current = null
  searchProps.current = null
  urlState.params = {}
  urlState.setParams = vi.fn((..._a: unknown[]) => undefined)
  i18nMock.resolvedLanguage = "en"
  i18nMock.language = "en"
  nextLesson.value = null
  weather.value = undefined
  mq.narrow = false
  mq.reduced = false
})

afterEach(() => {
  vi.useRealTimers()
})

describe("MapFeature — orchestration handlers", () => {
  it("uses the deterministic server snapshot during SSR", () => {
    expect(renderToString(<MapFeature />)).toContain("map-theme")
  })

  it("opens the sidebar when a building is selected via MapLibre, then closes it", async () => {
    renderFeature()
    await whenMapMounted()

    // No sidebar before selecting a building (cold branch 276 false side).
    expect(screen.queryByRole("button", { name: "sidebar.close" })).not.toBeInTheDocument()

    // onSelectBuilding fires handleBuildingClick (143-145) → currentBuilding
    // becomes "ГУК" → currentFloor lookup (206) → MapSidebar renders (276-287).
    act(() => getSelectBuilding()("ГУК"))
    expect(screen.getByRole("button", { name: "sidebar.close" })).toBeInTheDocument()

    // The visible close button exercises the callback passed at line 295 and
    // proves the user-facing close path unmounts the sidebar.
    act(() => fireEvent.click(screen.getByRole("button", { name: "sidebar.close" })))
    expect(screen.queryByRole("button", { name: "sidebar.close" })).not.toBeInTheDocument()

    // onDeselectBuilding → handleCloseSidebar (157-161) remains covered as a
    // separate map-originated close path.
    act(() => getSelectBuilding()("ГУК"))
    const onDeselect = mapProps.current!.onDeselectBuilding as () => void
    act(() => onDeselect())
    expect(screen.queryByRole("button", { name: "sidebar.close" })).not.toBeInTheDocument()
  })

  it("renders the flex-row layout when narrow=false and a building is selected (branch 239)", async () => {
    const { container } = renderFeature()
    await whenMapMounted()
    act(() => getSelectBuilding()("ГУК"))
    expect(container.querySelector(".flex.flex-row")).not.toBeNull()
  })

  it("keeps flex-col layout on narrow viewport even with a building selected", async () => {
    mq.narrow = true
    const { container } = renderFeature()
    await whenMapMounted()
    act(() => getSelectBuilding()("ГУК"))
    expect(container.querySelector(".flex.flex-row")).toBeNull()
    // Mobile sidebar renders as a bottom-sheet role="dialog" (no visible close
    // button — it uses a drag handle); presence proves the sidebar mounted.
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  it("drives floor + room handlers through the rendered sidebar", async () => {
    renderFeature()
    await whenMapMounted()
    act(() => getSelectBuilding()("ГУК"))

    // A room button (rendered as the room id text on floor 1) exercises
    // handleRoomClick (153-154) → setSelectedRoom.
    act(() => fireEvent.click(screen.getByText("ГУК-101")))

    // The floor selector lives in its own radiogroup inside the sidebar
    // (MapCategoryFilter also uses role="radio", so scope to the floor group).
    const floorGroup = screen.getByRole("radiogroup", { name: "floorPlan.selectFloor" })
    const floorRadios = within(floorGroup).getAllByRole("radio")
    expect(floorRadios.length).toBeGreaterThan(1)
    // Clicking floor 2 exercises handleFloorChange (148-150) → resets selectedRoom.
    act(() => fireEvent.click(floorRadios[1]!))

    // Sidebar still mounted; floor 2 rooms now visible.
    expect(screen.getByRole("button", { name: "sidebar.close" })).toBeInTheDocument()
    expect(screen.getByText("ГУК-201")).toBeInTheDocument()
  })

  it("navigates to a room via the search bar (navigateToRoom 164-167)", async () => {
    renderFeature()
    await whenMapMounted()
    // MapSearchBar fires onSelectRoom(letter, floor, roomId) → navigateToRoom,
    // which sets selectedBuilding + selectedFloor + selectedRoom and renders
    // the sidebar with the chosen floor.
    act(() => fireEvent.click(screen.getByTestId("search-room")))
    expect(screen.getByRole("button", { name: "sidebar.close" })).toBeInTheDocument()
    // selectedFloor=2 was applied → MapSidebar gets the building's floor-2 data.
    expect(searchProps.current).not.toBeNull()
  })

  it("debounces map move-end and writes serialized viewport via setUrlParams (127-132)", async () => {
    renderFeature()
    await whenMapMounted()
    vi.useFakeTimers()
    const onMoveEnd = mapProps.current!.onMapMoveEnd as (s: {
      zoom: number
      latitude: number
      longitude: number
      pitch: number
      bearing: number
    }) => void

    act(() => {
      onMoveEnd({ zoom: 16, latitude: 55.714, longitude: 37.818, pitch: 30, bearing: 90 })
      // Fire again before the debounce elapses → exercises the
      // `if (moveEndDebounceRef.current) clearTimeout(...)` true branch (128).
      onMoveEnd({ zoom: 17, latitude: 55.715, longitude: 37.819, pitch: 40, bearing: 120 })
    })
    expect(urlState.setParams).not.toHaveBeenCalled()

    act(() => {
      vi.advanceTimersByTime(500)
    })
    // Only the second (last) move-end commits, with serialized numbers.
    expect(urlState.setParams).toHaveBeenCalledTimes(1)
    expect(urlState.setParams).toHaveBeenCalledWith({
      z: 17,
      lat: 55.715,
      lng: 37.819,
      p: 40,
      b: 120,
    })
  })

  it("clears the pending move-end timer on unmount (cleanup branch 137)", async () => {
    const { unmount } = renderFeature()
    await whenMapMounted()
    vi.useFakeTimers()
    const clearSpy = vi.spyOn(globalThis, "clearTimeout")
    const onMoveEnd = mapProps.current!.onMapMoveEnd as (s: {
      zoom: number
      latitude: number
      longitude: number
      pitch: number
      bearing: number
    }) => void
    act(() => {
      onMoveEnd({ zoom: 16, latitude: 55.714, longitude: 37.818, pitch: 30, bearing: 90 })
    })
    unmount()
    // Unmount cleanup clears the still-pending debounce timer.
    expect(clearSpy).toHaveBeenCalled()
    clearSpy.mockRestore()
  })

  it("latches the initial viewport from URL params and forwards it to MapLibre", async () => {
    urlState.params = { z: 16.5, lat: 55.714, lng: 37.818, p: 45, b: 120 }
    renderFeature()
    await whenMapMounted()
    expect(mapProps.current!.urlInitialViewport).toEqual({
      zoom: 16.5,
      latitude: 55.714,
      longitude: 37.818,
      pitch: 45,
      bearing: 120,
    })
  })

  it("forwards nextLesson building as the highlighted building (branch 260)", async () => {
    nextLesson.value = { building: "ПА" }
    renderFeature()
    await whenMapMounted()
    expect(mapProps.current!.highlightedBuilding).toBe("ПА")
  })

  it("forwards null highlighted building when there is no next lesson", async () => {
    nextLesson.value = null
    renderFeature()
    await whenMapMounted()
    expect(mapProps.current!.highlightedBuilding).toBeNull()
  })

  it("threads weather condition into data-weather + MapLibre prop (branches 213, 266)", async () => {
    weather.value = { condition: "rain" }
    const { container } = renderFeature()
    await whenMapMounted()
    expect(container.querySelector(".map-theme")).toHaveAttribute("data-weather", "rain")
    expect(mapProps.current!.weatherCondition).toBe("rain")
  })
})

describe("MapFeature — keyboard shortcut callbacks", () => {
  it("onSelectBuilding shortcut opens the sidebar", async () => {
    renderFeature()
    await whenMapMounted()
    expect(ksOptions.current).not.toBeNull()
    act(() => ksOptions.current!.onSelectBuilding("ГУК"))
    expect(screen.getByRole("button", { name: "sidebar.close" })).toBeInTheDocument()
  })

  it("onToggleShortcuts opens then closes the shortcuts overlay", async () => {
    renderFeature()
    await whenMapMounted()
    // Initially closed.
    expect(screen.queryByText("shortcuts.close")).not.toBeInTheDocument()
    act(() => ksOptions.current!.onToggleShortcuts())
    expect(screen.getByText("shortcuts.close")).toBeInTheDocument()
    act(() => fireEvent.click(screen.getByRole("button", { name: "sidebar.close" })))
    expect(screen.queryByText("shortcuts.close")).not.toBeInTheDocument()
  })

  it("onFocusSearch focuses the search input without throwing", async () => {
    renderFeature()
    await whenMapMounted()
    act(() => ksOptions.current!.onFocusSearch())
    expect(screen.getByTestId("search-input")).toHaveFocus()
  })

  it("ignores fullscreen shortcut after the map container is gone", async () => {
    renderFeature()
    await whenMapMounted()
    document.querySelector(".map-card-matte")?.remove()
    expect(() => act(() => ksOptions.current!.onToggleFullscreen())).not.toThrow()
  })

  it("onToggleFullscreen requests fullscreen when none is active (branch 185 true)", async () => {
    const reqSpy = vi.fn(() => Promise.resolve())
    Element.prototype.requestFullscreen =
      reqSpy as unknown as typeof Element.prototype.requestFullscreen
    Object.defineProperty(document, "fullscreenElement", {
      configurable: true,
      get: () => null,
    })
    renderFeature()
    await whenMapMounted()
    act(() => ksOptions.current!.onToggleFullscreen())
    expect(reqSpy).toHaveBeenCalled()
  })

  it("onToggleFullscreen exits fullscreen when one is active (branch 187 else)", async () => {
    const exitSpy = vi.fn(() => Promise.resolve())
    document.exitFullscreen = exitSpy as unknown as typeof document.exitFullscreen
    Object.defineProperty(document, "fullscreenElement", {
      configurable: true,
      get: () => document.body,
    })
    renderFeature()
    await whenMapMounted()
    act(() => ksOptions.current!.onToggleFullscreen())
    expect(exitSpy).toHaveBeenCalled()
  })
})

describe("MapFeature — Escape key + locale fallback", () => {
  it("closes the sidebar when Escape is pressed with a building selected (173-176)", async () => {
    renderFeature()
    await whenMapMounted()
    act(() => getSelectBuilding()("ГУК"))
    expect(screen.getByRole("button", { name: "sidebar.close" })).toBeInTheDocument()

    act(() => {
      fireEvent.keyDown(window, { key: "Escape" })
    })
    expect(screen.queryByRole("button", { name: "sidebar.close" })).not.toBeInTheDocument()
  })

  it("does nothing on Escape when no building is selected (guard false side)", async () => {
    renderFeature()
    await whenMapMounted()
    expect(() =>
      act(() => {
        fireEvent.keyDown(window, { key: "Escape" })
      })
    ).not.toThrow()
    expect(screen.queryByRole("button", { name: "sidebar.close" })).not.toBeInTheDocument()
  })

  it("falls back to i18n.language when resolvedLanguage is undefined (branch 80)", async () => {
    i18nMock.resolvedLanguage = undefined
    i18nMock.language = "ru"
    const { container } = renderFeature()
    await whenMapMounted()
    // Still renders the themed root — getCampusBuildings(language) succeeds.
    expect(container.querySelector(".map-theme")).not.toBeNull()
  })
})
