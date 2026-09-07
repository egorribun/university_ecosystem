import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  activityGet: vi.fn(),
  allEvents: vi.fn(),
  myEvents: vi.fn(),
}))

vi.mock("@/api/client", () => ({ default: { get: mocks.activityGet } }))

vi.mock("@/api/generated/sdk.gen", () => ({
  allEventsApiV1EventsGet: (...args: unknown[]) => mocks.allEvents(...args),
  myEventsApiV1EventsMyGet: (...args: unknown[]) => mocks.myEvents(...args),
  getEventApiV1EventsEventIdGet: vi.fn(),
}))

import { ActivitySummaryUnavailableError, activitySummaryOptions } from "@/api/hooks/activity"
import {
  EVENTS_PAGE_SIZE,
  eventsListQueryKey,
  useEventsListQuery,
  useMyEventsQuery,
} from "@/api/hooks/events"
import { StorageItem } from "@/utils/storage"

const makeClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  })

const wrapperFor = (client: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return Wrapper
}

const runActivity = (signal?: AbortSignal) => {
  const options = activitySummaryOptions({ period: "30d", language: "en" })
  return options.queryFn?.({
    queryKey: options.queryKey,
    signal,
    meta: undefined,
    client: makeClient(),
  } as never)
}

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
  window.localStorage.clear()
})

describe("activity fallback mutation contracts", () => {
  it("handles a null primary error and an omitted signal without throwing while falling back", async () => {
    mocks.activityGet
      .mockRejectedValueOnce(null)
      .mockResolvedValueOnce({ data: { present: true } })
      .mockRejectedValueOnce(new Error("grades unavailable"))
      .mockResolvedValueOnce({ data: { score: 91 } })

    await expect(runActivity(undefined)).resolves.toEqual({
      attendance: { present: true },
      grades: null,
      participation: { score: 91 },
    })
  })

  it("returns partial fallback data when attendance succeeds and both other feeds fail", async () => {
    mocks.activityGet
      .mockRejectedValueOnce(new Error("summary unavailable"))
      .mockResolvedValueOnce({ data: { present: false } })
      .mockRejectedValueOnce(new Error("grades unavailable"))
      .mockRejectedValueOnce(new Error("participation unavailable"))

    await expect(runActivity(new AbortController().signal)).resolves.toEqual({
      attendance: { present: false },
      grades: null,
      participation: null,
    })
  })

  it("preserves the unavailable error only when every fallback feed rejects", async () => {
    mocks.activityGet
      .mockRejectedValueOnce(null)
      .mockRejectedValueOnce(new Error("attendance unavailable"))
      .mockRejectedValueOnce(new Error("grades unavailable"))
      .mockRejectedValueOnce(new Error("participation unavailable"))

    await expect(runActivity(undefined)).rejects.toBeInstanceOf(ActivitySummaryUnavailableError)
  })
})

describe("events filter and hydrated-state mutation contracts", () => {
  it.each([
    ["negative", -1],
    ["infinite", Number.POSITIVE_INFINITY],
    ["not-a-number", Number.NaN],
  ])("falls back to the canonical page size for a %s limit", (_label, limit) => {
    const key = eventsListQueryKey({ language: "en", limit })
    expect(key[2].limit).toBe(EVENTS_PAGE_SIZE)
  })

  it("retains the all-events ETag activity segment for a null filter", async () => {
    mocks.allEvents.mockResolvedValue({
      status: 200,
      data: {
        items: [],
        total: 0,
        limit: EVENTS_PAGE_SIZE,
        cursor: null,
        next_cursor: null,
        has_more: false,
      },
    })
    const client = makeClient()
    const { result } = renderHook(() => useEventsListQuery({ language: "en" }), {
      wrapper: wrapperFor(client),
    })

    await waitFor(() => expect(mocks.allEvents).toHaveBeenCalledOnce())
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const config = mocks.allEvents.mock.calls[0]?.[0] as { etagCacheKey?: string }
    expect(config.etagCacheKey).toBe("events:list:en:all:::12")
    expect(result.current.pagination?.limit).toBe(EVENTS_PAGE_SIZE)
  })

  it("fails closed when reading the persisted my-events placeholder throws", () => {
    vi.spyOn(StorageItem.prototype, "get").mockImplementation(() => {
      throw new Error("storage unavailable")
    })
    const client = makeClient()

    expect(() =>
      renderHook(() => useMyEventsQuery({ language: "en", userId: "user-1" }, { enabled: false }), {
        wrapper: wrapperFor(client),
      })
    ).not.toThrow()
  })
})
