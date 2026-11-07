import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { expect, it, vi } from "vitest"

import { MapFeature } from "@/features/map/MapFeature"
import { createI18nInstance } from "@/i18n/config"
import { useAuthStore } from "@/stores/useAuthStore"
import type { Event } from "@/types/Event"

const transport = vi.hoisted(() => ({
  allEvents: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
}))

// Keep MapFeature, useMapEvents, the infinite query, MapLibreMap and EventMarker
// real. Only the generated SDK response boundary replaces HTTP/backend work.
vi.mock("@/api/generated/sdk.gen", () => ({
  allEventsApiV1EventsGet: (...args: unknown[]) => transport.allEvents(...args),
  myEventsApiV1EventsMyGet: vi.fn(),
  myEventsPageApiV1EventsMyPageGet: vi.fn(),
}))

// Existing jsdom seam renders real marker children, but no WebGL, tiles or
// worker. This test proves accessible marker DOM, not canvas positioning.
vi.mock("react-map-gl/maplibre", async () =>
  (await import("@/tests/helpers/mapGlMock")).mapGlMock()
)
vi.mock("@/features/map/loadMapLibre", () => ({
  loadMapLibre: () =>
    import("@/components/map/MapLibreMap").then((module) => ({
      default: module.MapLibreMapComponent,
    })),
}))

// Unrelated schedule/weather/router work is outside this pagination boundary.
vi.mock("@/hooks/useNextLesson", () => ({ useNextLesson: () => null }))
vi.mock("@/hooks/useScheduleData", () => ({ useScheduleData: () => ({ todayLessons: [] }) }))
vi.mock("@/hooks/useMapWeather", () => ({
  useMapWeather: () => ({ data: undefined, isLoading: false }),
}))
vi.mock("@/hooks/useTimeOfDay", () => ({ useTimeOfDay: () => "afternoon" }))
vi.mock("@/hooks/useSeason", () => ({ useSeason: () => "spring" }))
vi.mock("@/hooks/useURLState", () => ({
  useURLState: () => ({ params: {}, setParams: vi.fn() }),
}))
vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)

type EventRequest = {
  query: {
    limit: number
    is_active: boolean
    search: string
    location: string
    cursor?: string
  }
}

const makeEvent = (number: number): Event => ({
  id: `map-event-${number}`,
  title: `Campus event ${number}`,
  title_en: `Campus event ${number}`,
  created_at: "2026-10-30T09:00:00Z",
  created_by: "map-pagination-author",
  starts_at: "2026-11-01T10:00:00Z",
  ends_at: "2026-11-01T11:00:00Z",
  is_active: true,
  is_registered: false,
  location: "ГУК-305",
  location_en: "ГУК-305",
  participant_count: 1,
  files: [],
})

it("appends the 51st map marker through the real cursor query and pending UI", async () => {
  const firstPage = Array.from({ length: 50 }, (_, index) => makeEvent(index + 1))
  const lastEvent = makeEvent(51)
  const cursor = "map-next/opaque+2="
  const requests: EventRequest["query"][] = []
  let releaseNextPage: () => void = () => undefined
  const pendingNextPage = new Promise<void>((resolve) => {
    releaseNextPage = resolve
  })
  const page = (items: Event[], current: string | null, next: string | null) => ({
    status: 200,
    data: {
      items,
      total: 51,
      limit: 50,
      cursor: current,
      next_cursor: next,
      has_more: next !== null,
    },
  })

  transport.allEvents.mockReset()
  transport.allEvents.mockImplementation(async (...args: unknown[]) => {
    const request = args[0] as EventRequest
    requests.push({ ...request.query })
    if (request.query.cursor === undefined) return page(firstPage, null, cursor)
    if (request.query.cursor !== cursor) throw new Error("Unexpected map cursor")
    await pendingNextPage
    return page([lastEvent], cursor, null)
  })

  const previousAuth = useAuthStore.getState()
  window.localStorage.clear()
  useAuthStore.setState({
    user: {
      id: "map-pagination-reader",
      email: "map-pagination@example.test",
      is_active: true,
    },
    loading: false,
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  const i18n = createI18nInstance("en")

  try {
    render(
      <I18nextProvider i18n={i18n}>
        <QueryClientProvider client={client}>
          <MapFeature />
        </QueryClientProvider>
      </I18nextProvider>
    )
    fireEvent.pointerDown(screen.getByTestId("map-activation-placeholder"))

    const firstMarker = await screen.findByRole("button", { name: "Event: Campus event 1" })
    expect(firstMarker).toBeVisible()
    const map = within(screen.getByRole("application"))
    const markerNames = () =>
      map
        .getAllByRole("button", { name: /^Event: Campus event / })
        .map((marker) => marker.getAttribute("aria-label"))
    const firstNames = firstPage.map((event) => `Event: ${event.title}`)
    expect(markerNames()).toEqual(firstNames)
    expect(requests).toEqual([{ limit: 50, is_active: true, search: "", location: "" }])
    expect(screen.queryByRole("button", { name: "Event: Campus event 51" })).toBeNull()

    const loadMore = screen.getByRole("button", { name: "Load more" })
    expect(loadMore).toBeEnabled()
    fireEvent.click(loadMore)
    await waitFor(() => {
      expect(loadMore).toBeDisabled()
      expect(loadMore).toHaveAttribute("aria-busy", "true")
    })
    expect(requests).toEqual([
      { limit: 50, is_active: true, search: "", location: "" },
      { limit: 50, is_active: true, search: "", location: "", cursor },
    ])
    expect(markerNames()).toEqual(firstNames)
    expect(screen.queryByRole("button", { name: "Event: Campus event 51" })).toBeNull()

    // The real disabled Button must not start another cursor request.
    await act(async () => {
      fireEvent.click(loadMore)
    })
    expect(requests).toHaveLength(2)

    await act(async () => {
      releaseNextPage()
      await pendingNextPage
    })
    const lastMarker = await screen.findByRole("button", { name: "Event: Campus event 51" })
    expect(lastMarker).toBeVisible()
    expect(markerNames()).toEqual([...firstNames, "Event: Campus event 51"])
    expect(firstMarker).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull()
    expect(client.isFetching()).toBe(0)
    expect(requests).toHaveLength(2)
  } finally {
    releaseNextPage()
    cleanup()
    client.clear()
    useAuthStore.setState({ user: previousAuth.user, loading: previousAuth.loading })
    window.localStorage.clear()
    transport.allEvents.mockReset()
  }
})
