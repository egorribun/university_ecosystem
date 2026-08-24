import { afterEach, describe, expect, it, vi } from "vitest"
import { renderHook } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"

import { useMapEvents } from "./useMapEvents"
import * as campusData from "@/data/campusBuildings"

/**
 * useMapEvents — fetches active events and resolves campus building
 * geo-coordinates for each. Events without a parseable / recognised
 * building are silently skipped.
 *
 * We mock useEventsListQuery so the hook receives controlled fixtures
 * and assert the mapping shape: building parsing → BUILDING_IDS gating
 * → geoCoords lookup from the campus building data.
 */

function newClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  })
}

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
}

const mockEventsState = vi.hoisted(() => ({
  events: [] as unknown[],
  isLoading: false,
}))

vi.mock("@/api/hooks/events", () => ({
  useEventsListQuery: () => ({
    events: mockEventsState.events,
    isLoading: mockEventsState.isLoading,
  }),
}))

const stubEventsHook = (events: unknown[], isLoading = false) => {
  mockEventsState.events = events
  mockEventsState.isLoading = isLoading
}

afterEach(() => {
  vi.restoreAllMocks()
  mockEventsState.events = []
  mockEventsState.isLoading = false
})

describe("useMapEvents — empty / loading", () => {
  it("returns empty events and propagates isLoading", () => {
    stubEventsHook([], true)
    const client = newClient()
    const { result } = renderHook(() => useMapEvents(), {
      wrapper: wrapper(client),
    })
    expect(result.current.events).toEqual([])
    expect(result.current.isLoading).toBe(true)
  })

  it("returns empty events when the upstream returns []", () => {
    stubEventsHook([], false)
    const client = newClient()
    const { result } = renderHook(() => useMapEvents(), {
      wrapper: wrapper(client),
    })
    expect(result.current.events).toEqual([])
    expect(result.current.isLoading).toBe(false)
  })
})

describe("useMapEvents — building resolution", () => {
  it("maps a recognised event to its building geoCoords", () => {
    const fixture = [
      {
        id: "e1",
        title: "Lecture",
        starts_at: "2026-05-15T10:00:00Z",
        ends_at: "2026-05-15T12:00:00Z",
        location: "ГУК-305",
        location_en: null,
        participant_count: 12,
      },
    ]
    stubEventsHook(fixture)
    const client = newClient()
    const { result } = renderHook(() => useMapEvents(), {
      wrapper: wrapper(client),
    })
    expect(result.current.events).toHaveLength(1)
    const ev = result.current.events[0]!
    expect(ev.id).toBe("e1")
    expect(ev.title).toBe("Lecture")
    expect(ev.buildingId).toBe("ГУК")
    expect(ev.location).toBe("ГУК-305")
    expect(ev.participantCount).toBe(12)
    // geoCoords is a [lat, lng] tuple resolved from campusBuildings.
    expect(ev.geoCoords).toHaveLength(2)
    expect(typeof ev.geoCoords[0]).toBe("number")
    expect(typeof ev.geoCoords[1]).toBe("number")
  })

  it("falls back to location_en when location is empty", () => {
    const fixture = [
      {
        id: "e2",
        title: "Practice",
        starts_at: "2026-05-15T10:00:00Z",
        ends_at: "2026-05-15T12:00:00Z",
        location: null,
        location_en: "ПА-201",
        participant_count: null,
      },
    ]
    stubEventsHook(fixture)
    const client = newClient()
    const { result } = renderHook(() => useMapEvents(), {
      wrapper: wrapper(client),
    })
    expect(result.current.events).toHaveLength(1)
    expect(result.current.events[0]!.buildingId).toBe("ПА")
    expect(result.current.events[0]!.location).toBe("ПА-201")
    // Optional participantCount becomes undefined (not null) when missing.
    expect(result.current.events[0]!.participantCount).toBeUndefined()
  })

  it("skips events without any location", () => {
    const fixture = [
      {
        id: "skip",
        title: "Off-site",
        starts_at: "2026-05-15T10:00:00Z",
        ends_at: "2026-05-15T12:00:00Z",
        location: null,
        location_en: null,
      },
    ]
    stubEventsHook(fixture)
    const client = newClient()
    const { result } = renderHook(() => useMapEvents(), {
      wrapper: wrapper(client),
    })
    expect(result.current.events).toEqual([])
  })

  it("skips events whose location does not match the building-room pattern", () => {
    const fixture = [
      {
        id: "no-dash",
        title: "X",
        starts_at: "2026-05-15T10:00:00Z",
        ends_at: "2026-05-15T12:00:00Z",
        // "Спорт. зал" — no dash → parseBuildingRoom returns null.
        location: "Спорт. зал",
        location_en: null,
      },
      {
        id: "non-numeric-room",
        title: "Y",
        starts_at: "2026-05-15T10:00:00Z",
        ends_at: "2026-05-15T12:00:00Z",
        // Dash present but room must start with a digit.
        location: "ГУК-room",
        location_en: null,
      },
    ]
    stubEventsHook(fixture)
    const client = newClient()
    const { result } = renderHook(() => useMapEvents(), {
      wrapper: wrapper(client),
    })
    expect(result.current.events).toEqual([])
  })

  it("skips events whose building is not in BUILDING_IDS", () => {
    const fixture = [
      {
        id: "unknown-building",
        title: "External",
        starts_at: "2026-05-15T10:00:00Z",
        ends_at: "2026-05-15T12:00:00Z",
        // 'XX' is not a valid GUU building.
        location: "XX-101",
        location_en: null,
      },
    ]
    stubEventsHook(fixture)
    const client = newClient()
    const { result } = renderHook(() => useMapEvents(), {
      wrapper: wrapper(client),
    })
    expect(result.current.events).toEqual([])
  })

  it("skips a recognized building when the localized catalog has no matching entry", () => {
    vi.spyOn(campusData, "getCampusBuildings").mockReturnValue([])
    stubEventsHook([
      {
        id: "missing-catalog-entry",
        title: "Temporarily unavailable building",
        starts_at: "2026-05-15T10:00:00Z",
        ends_at: "2026-05-15T12:00:00Z",
        location: "ГУК-305",
        location_en: null,
      },
    ])

    const client = newClient()
    const { result } = renderHook(() => useMapEvents(), {
      wrapper: wrapper(client),
    })

    expect(result.current.events).toEqual([])
  })

  it("preserves only valid events and drops invalid ones in mixed input", () => {
    const fixture = [
      {
        id: "ok-1",
        title: "Lecture",
        starts_at: "2026-05-15T10:00:00Z",
        ends_at: "2026-05-15T12:00:00Z",
        location: "ГУК-305",
        location_en: null,
      },
      {
        id: "skip-no-loc",
        title: "X",
        starts_at: "2026-05-15T10:00:00Z",
        ends_at: "2026-05-15T12:00:00Z",
        location: null,
        location_en: null,
      },
      {
        id: "ok-2",
        title: "Practice",
        starts_at: "2026-05-15T13:00:00Z",
        ends_at: "2026-05-15T15:00:00Z",
        location: "ПА-201",
        location_en: null,
      },
      {
        id: "skip-unknown",
        title: "External",
        starts_at: "2026-05-15T10:00:00Z",
        ends_at: "2026-05-15T12:00:00Z",
        location: "ZZ-1",
        location_en: null,
      },
    ]
    stubEventsHook(fixture)
    const client = newClient()
    const { result } = renderHook(() => useMapEvents(), {
      wrapper: wrapper(client),
    })
    const ids = result.current.events.map((e) => e.id)
    expect(ids).toEqual(["ok-1", "ok-2"])
  })
})
