/**
 * @fileoverview Wave session-15 branch top-up for `src/api/hooks/events.ts`.
 *
 * The existing `events.etag.test.tsx` drives `useEventsListQuery` happy-path
 * via MSW. This sibling targets the UNCOVERED closures + branches that the
 * MSW test never reaches:
 *
 *   - eventsListQueryKey() factory (77-79)
 *   - ensurePaginatedResponse() null-payload fallback (86-94) + 304 cached path
 *   - mergeEventPages() last-write-wins dedupe across pages (122)
 *   - createEventsListQueryFn cursor-param branch (149-151) + 304 fallback
 *   - useEventsListQuery placeholderData offline-success path (216-231)
 *   - prefetchEventsListQuery (262-272)
 *   - createMyEventsEtagKey / myEventsQueryKey (294, 297-299)
 *   - useMyEventsQuery placeholder + queryFn (200/304 paths) (329-354)
 *   - useSuspenseMyEventsQuery (385-417)
 *   - eventDetailQueryOptions.queryFn dynamic-import path (445-451)
 *   - useEventDetailQuery enabled guard (457-466)
 *   - useEventNavigation prev/next from cached list (482-525)
 *
 * NEVER hits MSW for /api paths (contract validator rejects off-schema
 * responses): the generated SDK module is vi.mock'd so the queryFn closures
 * see controlled responses.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { Event } from "@/types/Event"
import { StorageItem } from "@/utils/storage"

// ── SDK mock ────────────────────────────────────────────────────────────────
// The hooks/factories import `allEventsApiV1EventsGet` + `myEventsApiV1EventsMyGet`
// statically and `getEventApiV1EventsEventIdGet` dynamically. Mock all three.
const allEventsMock = vi.fn<(...args: unknown[]) => Promise<unknown>>()
const myEventsMock = vi.fn<(...args: unknown[]) => Promise<unknown>>()
const getEventMock = vi.fn<(...args: unknown[]) => Promise<unknown>>()

vi.mock("@/api/generated/sdk.gen", () => ({
  allEventsApiV1EventsGet: (...args: unknown[]) => allEventsMock(...args),
  myEventsApiV1EventsMyGet: (...args: unknown[]) => myEventsMock(...args),
  getEventApiV1EventsEventIdGet: (...args: unknown[]) => getEventMock(...args),
}))

import {
  eventsListQueryKey,
  prefetchEventsListQuery,
  myEventsQueryKey,
  useEventsListQuery,
  useMyEventsQuery,
  useSuspenseMyEventsQuery,
  eventDetailQueryOptions,
  useEventDetailQuery,
  useEventNavigation,
} from "@/api/hooks/events"

const makeEvent = (id: string, title = `Event ${id}`): Event =>
  ({
    id,
    title,
    created_at: "2026-01-15T10:00:00.000Z",
    starts_at: "2026-01-20T10:00:00.000Z",
    ends_at: "2026-01-20T12:00:00.000Z",
  }) as unknown as Event

const okPage = (items: Event[], next_cursor: string | null = null) => ({
  status: 200,
  data: {
    items,
    total: items.length,
    limit: 12,
    cursor: null,
    next_cursor,
    has_more: next_cursor != null,
  },
})

const makeWrapper = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return Wrapper
}

const freshClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })

beforeEach(() => {
  allEventsMock.mockReset()
  myEventsMock.mockReset()
  getEventMock.mockReset()
  if (typeof window !== "undefined") window.localStorage.clear()
})

afterEach(() => {
  if (typeof window !== "undefined") window.localStorage.clear()
})

// ── eventsListQueryKey factory (77-79) ────────────────────────────────────────
describe("eventsListQueryKey (events.ts:77-79)", () => {
  it("normalizes filters into ['events', 'list', normalized]", () => {
    const key = eventsListQueryKey({ language: "ru", is_active: true })
    expect(key[0]).toBe("events")
    expect(key[1]).toBe("list")
    expect(key[2]).toEqual({
      language: "ru",
      is_active: true,
      search: "",
      location: "",
      limit: 12,
    })

    expect(eventsListQueryKey({ language: "ru", is_active: false })[2].is_active).toBe(false)
    expect(eventsListQueryKey({ language: "ru", is_active: null })[2].is_active).toBeNull()
    expect(eventsListQueryKey({ language: "ru", limit: 3.9 })[2].limit).toBe(3)
  })

  it("normalizes is_active=null/undefined to null and trims search/location", () => {
    const key = eventsListQueryKey({
      language: "en",
      is_active: null,
      search: "  hello  ",
      location: "  campus  ",
      limit: 25.7,
    })
    expect(key[2]).toEqual({
      language: "en",
      is_active: null,
      search: "hello",
      location: "campus",
      limit: 25, // floored
    })
  })

  it("falls back to page size for non-positive / non-finite limit", () => {
    expect(eventsListQueryKey({ language: "ru", limit: 0 })[2].limit).toBe(12)
    expect(eventsListQueryKey({ language: "ru", limit: -5 })[2].limit).toBe(12)
    expect(eventsListQueryKey({ language: "ru", limit: Number.NaN })[2].limit).toBe(12)
  })

  it("exposes the same canonical key from the hook", () => {
    const queryClient = freshClient()
    const { result } = renderHook(
      () =>
        useEventsListQuery(
          { language: "en", is_active: false, search: "  library  " },
          { enabled: false }
        ),
      { wrapper: makeWrapper(queryClient) }
    )

    expect(result.current.queryKey).toEqual([
      "events",
      "list",
      { language: "en", is_active: false, search: "library", location: "", limit: 12 },
    ])
  })
})

// ── useEventsListQuery: queryFn null-fallback (86-94) + cursor (149-151) + 304 ─
describe("useEventsListQuery queryFn branches", () => {
  it("ensurePaginatedResponse fallback when response.data is null (86-94)", async () => {
    allEventsMock.mockResolvedValue({ status: 200, data: null })

    const queryClient = freshClient()
    const { result } = renderHook(() => useEventsListQuery({ language: "ru", is_active: true }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.events).toEqual([])
    expect(result.current.pagination).toEqual({
      items: [],
      total: 0,
      limit: 12,
      cursor: null,
      next_cursor: null,
      has_more: false,
    })
  })

  it("normalizes malformed pagination fields to safe defaults", async () => {
    allEventsMock.mockResolvedValue({
      status: 200,
      data: { items: "invalid", total: "invalid", limit: "invalid" },
    })

    const queryClient = freshClient()
    const { result } = renderHook(() => useEventsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.pagination).toMatchObject({ items: [], total: 0, limit: 12 })
  })

  it("preserves valid pagination fields and sends the complete first-page contract", async () => {
    const item = makeEvent("numeric-fields")
    allEventsMock.mockResolvedValue({
      status: 200,
      data: {
        items: [item],
        total: 99,
        limit: 7,
        cursor: "server-cursor",
        next_cursor: null,
        has_more: false,
      },
    })

    const queryClient = freshClient()
    const { result } = renderHook(
      () =>
        useEventsListQuery({
          language: "ru",
          is_active: null,
          search: "  query  ",
          location: "  campus  ",
          limit: 5,
        }),
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.pagination).toMatchObject({
      items: [item],
      total: 99,
      limit: 7,
      cursor: "server-cursor",
      next_cursor: null,
      has_more: false,
    })

    const request = allEventsMock.mock.calls[0]?.[0] as {
      query?: Record<string, unknown>
      etagCacheKey?: string
      validateStatus?: (status: number) => boolean
    }
    expect(request.query).toEqual({ limit: 5, search: "query", location: "campus" })
    expect(request.query).not.toHaveProperty("is_active")
    expect(request.query).not.toHaveProperty("cursor")
    expect(request.etagCacheKey).toBe("events:list:ru:all:query:campus:5")
    expect(request.validateStatus?.(199)).toBe(false)
    expect(request.validateStatus?.(200)).toBe(true)
    expect(request.validateStatus?.(399)).toBe(true)
    expect(request.validateStatus?.(400)).toBe(false)
  })

  it("passes cursor param + merges via getNextPageParam on fetchNextPage (149-151)", async () => {
    const firstPage = [makeEvent("a"), makeEvent("b")]
    const secondPage = [makeEvent("c")]
    allEventsMock
      .mockResolvedValueOnce(okPage(firstPage, "cursor-2"))
      .mockResolvedValueOnce(okPage(secondPage, null))

    const queryClient = freshClient()
    const { result } = renderHook(() => useEventsListQuery({ language: "ru", is_active: true }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.events).toHaveLength(2))
    expect(result.current.hasNextPage).toBe(true)

    await act(async () => {
      await result.current.fetchNextPage()
    })

    await waitFor(() => expect(result.current.events).toHaveLength(3))
    // second call sent the cursor param
    const secondCall = allEventsMock.mock.calls[1]?.[0] as { query?: Record<string, unknown> }
    expect(secondCall?.query?.cursor).toBe("cursor-2")
  })

  it("uses ETag only for the first page and carries the cursor on later pages", async () => {
    allEventsMock
      .mockResolvedValueOnce(okPage([makeEvent("etag-first")], "cursor-2"))
      .mockResolvedValueOnce(okPage([makeEvent("etag-second")], null))

    const queryClient = freshClient()
    const { result } = renderHook(() => useEventsListQuery({ language: "ru", is_active: true }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.hasNextPage).toBe(true))
    const firstCall = allEventsMock.mock.calls[0]?.[0] as {
      query?: Record<string, unknown>
      etagCacheKey?: string
    }
    expect(firstCall.query).not.toHaveProperty("cursor")
    expect(firstCall.etagCacheKey).toBe("events:list:ru:active:::12")

    await act(async () => {
      await result.current.fetchNextPage()
    })
    await waitFor(() => expect(result.current.events).toHaveLength(2))

    const secondCall = allEventsMock.mock.calls[1]?.[0] as {
      query?: Record<string, unknown>
      etagCacheKey?: string
    }
    expect(secondCall.query).toEqual({
      limit: 12,
      search: "",
      location: "",
      is_active: true,
      cursor: "cursor-2",
    })
    expect(secondCall).not.toHaveProperty("etagCacheKey")
  })

  it("304 response falls back to cached first page", async () => {
    const cachedItems = [makeEvent("z1"), makeEvent("z2")]
    allEventsMock
      .mockResolvedValueOnce(okPage(cachedItems, null))
      .mockResolvedValueOnce({ status: 304, data: undefined })

    const queryClient = freshClient()
    const { result } = renderHook(() => useEventsListQuery({ language: "ru", is_active: true }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.events).toHaveLength(2))

    await act(async () => {
      await result.current.refetch()
    })

    await waitFor(() => expect(result.current.isFetching).toBe(false))
    // cached fallback preserved the items
    expect(result.current.events).toHaveLength(2)
  })

  it("reports null pagination while an uncached request is pending", async () => {
    let resolveRequest: (value: unknown) => void = () => {}
    allEventsMock.mockImplementation(
      () => new Promise((resolve) => (resolveRequest = resolve as (value: unknown) => void))
    )

    const queryClient = freshClient()
    const { result } = renderHook(() => useEventsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isPending).toBe(true))
    expect(result.current.pagination).toBeNull()

    await act(async () => resolveRequest(okPage([], null)))
  })

  it("304 response with a malformed or cold cache safely returns an empty page", async () => {
    allEventsMock.mockResolvedValue({ status: 304, data: undefined })

    const queryClient = freshClient()
    // With no cached infinite-query entry the optional pages chain must treat
    // the 304 as a cache miss, not dereference an undefined cache value.
    const { result } = renderHook(() => useEventsListQuery({ language: "ru", is_active: true }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.events).toEqual([])
    expect(result.current.pagination).toEqual({
      items: [],
      total: 0,
      limit: 12,
      cursor: null,
      next_cursor: null,
      has_more: false,
    })
  })
})

// ── useEventsListQuery placeholderData offline-success path (216-231) ─────────
describe("useEventsListQuery placeholderData offline (events.ts:216-231)", () => {
  it("seeds events from localStorage when no network response yet", async () => {
    const stored = [makeEvent("p1"), makeEvent("p2")]
    // key shape: events:list:<language>:<activity>; is_active=true → "active"
    window.localStorage.setItem("events:list:ru:active", JSON.stringify(stored))

    // queryFn never resolves so placeholder is the only data source
    let resolveFn: (v: unknown) => void = () => {}
    allEventsMock.mockImplementation(
      () => new Promise((resolve) => (resolveFn = resolve as (v: unknown) => void))
    )

    const queryClient = freshClient()
    const { result } = renderHook(() => useEventsListQuery({ language: "ru", is_active: true }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.events).toEqual(stored))
    expect(result.current.data).toEqual({
      pages: [
        expect.objectContaining({
          items: stored,
          total: 2,
          limit: 12,
          cursor: null,
          next_cursor: null,
          has_more: false,
        }),
      ],
      pageParams: [null],
    })
    expect(result.current.pagination).toMatchObject({
      total: 2,
      limit: 12,
      has_more: false,
    })

    // resolve the pending fetch so the test can unwind cleanly
    await act(async () => {
      resolveFn(okPage(stored, null))
    })
  })

  it("returns no placeholder when stored items are empty/missing", async () => {
    window.localStorage.setItem("events:list:ru:archive", JSON.stringify([]))
    allEventsMock.mockResolvedValue(okPage([], null))

    const queryClient = freshClient()
    const { result } = renderHook(() => useEventsListQuery({ language: "ru", is_active: false }), {
      wrapper: makeWrapper(queryClient),
    })
    // empty stored → no placeholder → starts as loading
    expect(result.current.events).toEqual([])
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })

  it("uses distinct all/archive snapshots and preserves the infinite-page shape", () => {
    const scenarios = [
      { is_active: null, activity: "all", id: "all-snapshot" },
      { is_active: false, activity: "archive", id: "archive-snapshot" },
    ] as const

    for (const scenario of scenarios) {
      const stored = [makeEvent(scenario.id)]
      const key = `events:list:ru:${scenario.activity}`
      window.localStorage.setItem(key, JSON.stringify(stored))
      const queryClient = freshClient()
      const { result, unmount } = renderHook(
        () =>
          useEventsListQuery({ language: "ru", is_active: scenario.is_active }, { enabled: false }),
        { wrapper: makeWrapper(queryClient) }
      )

      expect(result.current.data).toEqual({
        pages: [
          {
            items: stored,
            total: 1,
            limit: 12,
            cursor: null,
            next_cursor: null,
            has_more: false,
          },
        ],
        pageParams: [null],
      })
      unmount()
      window.localStorage.removeItem(key)
    }
  })

  it("does not create a placeholder for non-array or empty persisted values", () => {
    for (const value of [{ invalid: true }, []]) {
      window.localStorage.setItem("events:list:ru:all", JSON.stringify(value))
      const queryClient = freshClient()
      const { result, unmount } = renderHook(
        () => useEventsListQuery({ language: "ru", is_active: null }, { enabled: false }),
        { wrapper: makeWrapper(queryClient) }
      )
      expect(result.current.data).toBeUndefined()
      unmount()
      window.localStorage.removeItem("events:list:ru:all")
    }
  })

  it("placeholder swallows malformed JSON gracefully", async () => {
    window.localStorage.setItem("events:list:ru:all", "{not-json")
    allEventsMock.mockResolvedValue(okPage([], null))

    const queryClient = freshClient()
    const { result } = renderHook(() => useEventsListQuery({ language: "ru", is_active: null }), {
      wrapper: makeWrapper(queryClient),
    })
    // malformed → no placeholder → loading until network
    expect(result.current.events).toEqual([])
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })

  it("returns no placeholder when the storage adapter throws", async () => {
    const getItemSpy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage unavailable")
    })
    allEventsMock.mockResolvedValue(okPage([], null))

    try {
      const queryClient = freshClient()
      const { result } = renderHook(() => useEventsListQuery({ language: "ru" }), {
        wrapper: makeWrapper(queryClient),
      })
      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(result.current.events).toEqual([])
    } finally {
      getItemSpy.mockRestore()
    }
  })
})

// ── mergeEventPages last-write-wins dedupe (events.ts:122) ─────────────────────
describe("mergeEventPages dedupe (events.ts:122 via two pages with shared id)", () => {
  it("later page overwrites the earlier item with the same id", async () => {
    const page1 = [makeEvent("dup", "OLD title"), makeEvent("solo")]
    const page2 = [makeEvent("dup", "NEW title")]
    allEventsMock
      .mockResolvedValueOnce(okPage(page1, "next"))
      .mockResolvedValueOnce(okPage(page2, null))

    const queryClient = freshClient()
    const { result } = renderHook(() => useEventsListQuery({ language: "ru", is_active: true }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.events).toHaveLength(2))
    await act(async () => {
      await result.current.fetchNextPage()
    })
    await waitFor(() => expect(result.current.events).toHaveLength(2))

    const dup = result.current.events.find((e) => e.id === "dup")
    expect(dup?.title).toBe("NEW title")
  })
})

// ── prefetchEventsListQuery (events.ts:262-272) ───────────────────────────────
describe("prefetchEventsListQuery (events.ts:262-272)", () => {
  it("calls prefetchInfiniteQuery with normalized key + cursor pagination shape", async () => {
    const queryClient = freshClient()
    const spy = vi.spyOn(queryClient, "prefetchInfiniteQuery").mockResolvedValue(undefined)

    await prefetchEventsListQuery(queryClient, { language: "en", is_active: true })

    expect(spy).toHaveBeenCalledOnce()
    const opts = spy.mock.calls[0]?.[0] as unknown as {
      queryKey: readonly [string, string, { language: string }]
      initialPageParam: string | null
      getNextPageParam: (p: { next_cursor: string | null }) => string | null
    }
    expect(opts.queryKey[0]).toBe("events")
    expect(opts.queryKey[1]).toBe("list")
    expect(opts.queryKey[2].language).toBe("en")
    expect(opts.initialPageParam).toBeNull()
    expect(opts.getNextPageParam({ next_cursor: "c" })).toBe("c")
    expect(opts.getNextPageParam({ next_cursor: null })).toBeNull()
    expect(opts.getNextPageParam(undefined as never)).toBeNull()
  })

  it("executes the real queryFn against the mocked SDK when not spied", async () => {
    const queryClient = freshClient()
    allEventsMock.mockResolvedValue(okPage([makeEvent("pf1")], null))

    await prefetchEventsListQuery(queryClient, { language: "ru" })

    expect(allEventsMock).toHaveBeenCalled()
    const cached = queryClient.getQueryData(eventsListQueryKey({ language: "ru" }))
    expect(cached).toBeDefined()
  })
})

// ── myEventsQueryKey + createMyEventsEtagKey (events.ts:294, 297-299) ─────────
describe("myEventsQueryKey (events.ts:294, 297-299)", () => {
  it("normalizes userId undefined → null", () => {
    const key = myEventsQueryKey({ language: "ru" })
    expect(key).toEqual(["events", "my", { language: "ru", userId: null }])
  })

  it("reflects an explicit userId", () => {
    const key = myEventsQueryKey({ language: "en", userId: "u-9" })
    expect(key[2]).toEqual({ language: "en", userId: "u-9" })
  })
})

// ── useMyEventsQuery placeholder + queryFn 200/304 (events.ts:329-354) ────────
describe("useMyEventsQuery (events.ts:329-354)", () => {
  it("disabled when userId is null (no fetch)", () => {
    const queryClient = freshClient()
    const { result } = renderHook(() => useMyEventsQuery({ language: "ru", userId: null }), {
      wrapper: makeWrapper(queryClient),
    })
    expect(result.current.fetchStatus).toBe("idle")
    expect(myEventsMock).not.toHaveBeenCalled()
    expect(result.current.queryKey).toEqual(["events", "my", { language: "ru", userId: null }])
  })

  it("uses the anonymous ETag sentinel when a disabled query is manually refetched", async () => {
    myEventsMock.mockResolvedValue({ status: 200, data: [] })
    const queryClient = freshClient()
    const { result } = renderHook(() => useMyEventsQuery({ language: "ru", userId: null }), {
      wrapper: makeWrapper(queryClient),
    })

    await act(async () => {
      await result.current.refetch()
    })

    expect(myEventsMock).toHaveBeenCalledOnce()
    expect(myEventsMock.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({ etagCacheKey: "events:my:ru:anon" })
    )
  })

  it("seeds placeholder from localStorage then resolves 200 array", async () => {
    const stored = [makeEvent("m-stored")]
    window.localStorage.setItem("events:my:ru:u-1", JSON.stringify(stored))
    const fresh = [makeEvent("m-fresh-1"), makeEvent("m-fresh-2")]
    myEventsMock.mockResolvedValue({ status: 200, data: fresh })

    const queryClient = freshClient()
    const { result } = renderHook(() => useMyEventsQuery({ language: "ru", userId: "u-1" }), {
      wrapper: makeWrapper(queryClient),
    })

    // placeholder visible first, then fresh
    await waitFor(() => expect(result.current.data).toEqual(fresh))
    expect(myEventsMock).toHaveBeenCalledOnce()
    const validateStatus = (
      myEventsMock.mock.calls[0]?.[0] as { validateStatus: (status: number) => boolean }
    ).validateStatus
    expect(validateStatus(200)).toBe(true)
    expect(validateStatus(400)).toBe(false)
  })

  it("exposes the user-scoped query key and placeholder while the request is pending", async () => {
    const stored = [makeEvent("m-persisted")]
    window.localStorage.setItem("events:my:ru:u-pending", JSON.stringify(stored))
    let resolveRequest: (value: unknown) => void = () => {}
    myEventsMock.mockImplementation(
      () => new Promise((resolve) => (resolveRequest = resolve as (value: unknown) => void))
    )

    const queryClient = freshClient()
    const { result } = renderHook(() => useMyEventsQuery({ language: "ru", userId: "u-pending" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.data).toEqual(stored))
    expect(result.current.queryKey).toEqual([
      "events",
      "my",
      { language: "ru", userId: "u-pending" },
    ])
    await act(async () => resolveRequest({ status: 200, data: stored }))
  })

  it("does not create a placeholder for a non-array persisted value", () => {
    window.localStorage.setItem("events:my:ru:u-invalid", JSON.stringify({ items: [] }))
    const queryClient = freshClient()
    const { result } = renderHook(
      () => useMyEventsQuery({ language: "ru", userId: "u-invalid" }, { enabled: false }),
      { wrapper: makeWrapper(queryClient) }
    )
    expect(result.current.data).toBeUndefined()
  })

  it("non-array 200 data coerces to [] (events.ts:353)", async () => {
    myEventsMock.mockResolvedValue({ status: 200, data: { unexpected: true } })
    const queryClient = freshClient()
    const { result } = renderHook(() => useMyEventsQuery({ language: "ru", userId: "u-x" }), {
      wrapper: makeWrapper(queryClient),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([])
  })

  it("304 response falls back to cached query data (events.ts:349-350)", async () => {
    const cached = [makeEvent("c-1")]
    myEventsMock
      .mockResolvedValueOnce({ status: 200, data: cached })
      .mockResolvedValueOnce({ status: 304, data: undefined })

    const queryClient = freshClient()
    const { result } = renderHook(() => useMyEventsQuery({ language: "ru", userId: "u-cache" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.data).toEqual(cached))

    await act(async () => {
      await result.current.refetch()
    })

    await waitFor(() => expect(result.current.isFetching).toBe(false))
    expect(result.current.data).toEqual(cached)
  })

  it("304 response uses safe pagination defaults when cached data has no pages", async () => {
    const queryClient = freshClient()
    queryClient.setQueryData(eventsListQueryKey({ language: "ru", is_active: true }), {
      pages: [],
      pageParams: [],
    })
    allEventsMock.mockResolvedValue({ status: 304, data: undefined })

    const { result } = renderHook(() => useEventsListQuery({ language: "ru", is_active: true }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(allEventsMock).toHaveBeenCalledOnce())
    await waitFor(() => expect(result.current.isFetching).toBe(false))
    expect(result.current.events).toEqual([])
    expect(result.current.pagination).toMatchObject({ items: [], total: 0, limit: 12 })
  })

  it("304 response returns an empty array when no cached my-events data exists", async () => {
    myEventsMock.mockResolvedValue({ status: 304, data: undefined })

    const queryClient = freshClient()
    const { result } = renderHook(() => useMyEventsQuery({ language: "ru", userId: "u-empty" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([])
  })

  it("placeholder swallows malformed JSON for the my-events key", async () => {
    window.localStorage.setItem("events:my:ru:u-bad", "{broken")
    myEventsMock.mockResolvedValue({ status: 200, data: [] })

    const queryClient = freshClient()
    const { result } = renderHook(() => useMyEventsQuery({ language: "ru", userId: "u-bad" }), {
      wrapper: makeWrapper(queryClient),
    })
    expect(result.current.data).toBeUndefined() // no placeholder
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })

  it("returns no placeholder when the storage adapter throws", async () => {
    const getSpy = vi.spyOn(StorageItem.prototype, "get").mockImplementation(() => {
      throw new Error("storage unavailable")
    })
    myEventsMock.mockResolvedValue({ status: 200, data: [] })

    try {
      const queryClient = freshClient()
      const { result } = renderHook(() => useMyEventsQuery({ language: "ru", userId: "u-throw" }), {
        wrapper: makeWrapper(queryClient),
      })
      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(result.current.data).toEqual([])
    } finally {
      getSpy.mockRestore()
    }
  })
})

// ── useSuspenseMyEventsQuery (events.ts:385-417) ─────────────────────────────
describe("useSuspenseMyEventsQuery (events.ts:385-417)", () => {
  it("resolves the suspense query against a 200 array", async () => {
    const data = [makeEvent("s-1"), makeEvent("s-2")]
    myEventsMock.mockResolvedValue({ status: 200, data })

    const queryClient = freshClient()
    const { result } = renderHook(
      () => useSuspenseMyEventsQuery({ language: "ru", userId: "su-1" }),
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(result.current.data).toEqual(data))
    expect(result.current.queryKey).toEqual(["events", "my", { language: "ru", userId: "su-1" }])
    const validateStatus = (
      myEventsMock.mock.calls[0]?.[0] as { validateStatus: (status: number) => boolean }
    ).validateStatus
    expect(validateStatus(199)).toBe(false)
    expect(validateStatus(200)).toBe(true)
    expect(validateStatus(299)).toBe(true)
    expect(validateStatus(399)).toBe(true)
    expect(validateStatus(400)).toBe(false)
    expect(validateStatus(500)).toBe(false)
  })

  it("non-array 200 data coerces to [] in suspense path (events.ts:409)", async () => {
    myEventsMock.mockResolvedValue({ status: 200, data: null })
    const queryClient = freshClient()
    const { result } = renderHook(
      () => useSuspenseMyEventsQuery({ language: "ru", userId: "su-2" }),
      { wrapper: makeWrapper(queryClient) }
    )
    await waitFor(() => expect(result.current.data).toEqual([]))
  })

  it("304 in suspense path falls back to cached data (events.ts:405-406)", async () => {
    const cached = [makeEvent("su-c")]
    const queryClient = freshClient()
    // pre-seed the cache so the 304 branch can read it
    // Mark the seed stale so the suspense query executes its 304 fallback
    // instead of short-circuiting on a fresh cache entry.
    queryClient.setQueryData(["events", "my", { language: "ru", userId: "su-3" }], cached, {
      updatedAt: 0,
    })
    myEventsMock.mockResolvedValue({ status: 304, data: undefined })

    const { result } = renderHook(
      () => useSuspenseMyEventsQuery({ language: "ru", userId: "su-3" }),
      { wrapper: makeWrapper(queryClient) }
    )
    await waitFor(() => expect(result.current.data).toEqual(cached))
    expect(myEventsMock).toHaveBeenCalledOnce()
  })

  it("304 in suspense path returns the cached identity even when the response carries data", async () => {
    const cached = [makeEvent("su-cached")]
    const responseData = [makeEvent("su-response")]
    const queryClient = freshClient()
    const queryKey = myEventsQueryKey({ language: "ru", userId: "su-identity" })
    queryClient.setQueryData(queryKey, cached, { updatedAt: 0 })
    myEventsMock.mockResolvedValue({ status: 304, data: responseData })

    const { result } = renderHook(
      () => useSuspenseMyEventsQuery({ language: "ru", userId: "su-identity" }),
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(myEventsMock).toHaveBeenCalledOnce())
    await waitFor(() => expect(result.current.isFetching).toBe(false))
    await waitFor(() => expect(result.current.data).toBe(cached))
    expect(result.current.data).not.toBe(responseData)
  })

  it("304 in suspense path returns an empty array when no cache exists", async () => {
    myEventsMock.mockResolvedValue({ status: 304, data: undefined })
    const queryClient = freshClient()
    const { result } = renderHook(
      () => useSuspenseMyEventsQuery({ language: "ru", userId: "su-empty-cache" }),
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(result.current.data).toEqual([]))
  })
})

// ── eventDetailQueryOptions.queryFn dynamic import (events.ts:445-451) ────────
describe("eventDetailQueryOptions.queryFn (events.ts:445-451)", () => {
  it("dynamically imports the SDK and returns response.data", async () => {
    const ev = makeEvent("detail-1", "Detail title")
    getEventMock.mockResolvedValue({ status: 200, data: ev })

    const opts = eventDetailQueryOptions("detail-1")
    const out = await opts.queryFn({ signal: undefined })

    expect(out).toEqual(ev)
    expect(getEventMock).toHaveBeenCalledWith(
      expect.objectContaining({ path: { event_id: "detail-1" } })
    )
  })
})

// ── useEventDetailQuery enabled guard (events.ts:457-466) ─────────────────────
describe("useEventDetailQuery (events.ts:457-466)", () => {
  it("does not fetch when id is undefined (enabled: !!id)", () => {
    const queryClient = freshClient()
    const { result } = renderHook(() => useEventDetailQuery(undefined), {
      wrapper: makeWrapper(queryClient),
    })
    expect(result.current.fetchStatus).toBe("idle")
    expect(getEventMock).not.toHaveBeenCalled()
    expect(queryClient.getQueryCache().find({ queryKey: ["events", "detail", ""] })).toBeDefined()
  })

  it("fetches the event when id is provided", async () => {
    const ev = makeEvent("d-2", "Hooked detail")
    getEventMock.mockResolvedValue({ status: 200, data: ev })

    const queryClient = freshClient()
    const { result } = renderHook(() => useEventDetailQuery("d-2"), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.data).toEqual(ev))
    expect(getEventMock).toHaveBeenCalledWith(
      expect.objectContaining({ path: { event_id: "d-2" } })
    )
  })
})

// ── useEventNavigation (events.ts:482-525) ────────────────────────────────────
describe("useEventNavigation (events.ts:482-525)", () => {
  it("derives prev/next from the cached events list, dedup preserving order", () => {
    const queryClient = freshClient()
    // A non-events cache entry must never influence event navigation. A
    // malformed query-key filter would include this page and change the
    // neighboring event ids.
    queryClient.setQueryData(["users", "me"], {
      pages: [{ items: [makeEvent("unrelated")] }],
    })
    // Two cached list entries with an overlapping id ("b") to exercise dedupe.
    queryClient.setQueryData(["events", "list", { language: "ru", page: 1 }], {
      pages: [{ items: [makeEvent("a", "A"), makeEvent("b", "B")] }],
    })
    queryClient.setQueryData(["events", "list", { language: "ru", page: 2 }], {
      pages: [{ items: [makeEvent("b", "B-dup"), makeEvent("c", "C")] }],
    })

    const { result } = renderHook(() => useEventNavigation("b"), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.prevId).toBe("a")
    expect(result.current.prevTitle).toBe("A")
    expect(result.current.nextId).toBe("c")
    expect(result.current.nextTitle).toBe("C")
  })

  it("only reads event-list query entries when deriving neighbors", () => {
    const queryClient = freshClient()
    queryClient.setQueryData(["users", "me"], {
      pages: [{ items: [makeEvent("foreign-before"), makeEvent("foreign-after")] }],
    })
    queryClient.setQueryData(["events", "list", { language: "ru" }], {
      pages: [{ items: [makeEvent("current"), makeEvent("next")] }],
    })

    const { result } = renderHook(() => useEventNavigation("current"), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.prevId).toBeNull()
    expect(result.current.prevTitle).toBeNull()
    expect(result.current.nextId).toBe("next")
    expect(result.current.nextTitle).toBe("Event next")
  })

  it("handles undefined cache data without dereferencing it", () => {
    const queryClient = freshClient()
    vi.spyOn(queryClient, "getQueriesData").mockReturnValue([
      [["events", "list"], undefined],
    ] as never)

    const { result } = renderHook(() => useEventNavigation("missing"), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current).toEqual({
      prevId: null,
      nextId: null,
      prevTitle: null,
      nextTitle: null,
    })
  })

  it("recomputes neighbors when the current id changes", () => {
    const queryClient = freshClient()
    queryClient.setQueryData(["events", "list", { language: "ru" }], {
      pages: [{ items: [makeEvent("a", "A"), makeEvent("b", "B"), makeEvent("c", "C")] }],
    })

    const { result, rerender } = renderHook(
      ({ currentId }: { currentId: string }) => useEventNavigation(currentId),
      {
        initialProps: { currentId: "a" },
        wrapper: makeWrapper(queryClient),
      }
    )
    expect(result.current.nextId).toBe("b")
    rerender({ currentId: "b" })
    expect(result.current.prevId).toBe("a")
    expect(result.current.nextId).toBe("c")
  })

  it("returns null nav for the first item (no prev)", () => {
    const queryClient = freshClient()
    queryClient.setQueryData(["events", "list", { language: "ru" }], {
      pages: [{ items: [makeEvent("first"), makeEvent("second")] }],
    })

    const { result } = renderHook(() => useEventNavigation("first"), {
      wrapper: makeWrapper(queryClient),
    })
    expect(result.current.prevId).toBeNull()
    expect(result.current.prevTitle).toBeNull()
    expect(result.current.nextId).toBe("second")
  })

  it("returns null nav for the last item (no next)", () => {
    const queryClient = freshClient()
    queryClient.setQueryData(["events", "list", { language: "ru" }], {
      pages: [{ items: [makeEvent("one"), makeEvent("two")] }],
    })

    const { result } = renderHook(() => useEventNavigation("two"), {
      wrapper: makeWrapper(queryClient),
    })
    expect(result.current.nextId).toBeNull()
    expect(result.current.nextTitle).toBeNull()
    expect(result.current.prevId).toBe("one")
  })

  it("returns the full fallback when currentId is not in the cached list", () => {
    const queryClient = freshClient()
    queryClient.setQueryData(["events", "list", { language: "ru" }], {
      pages: [{ items: [makeEvent("x")] }],
    })

    const { result } = renderHook(() => useEventNavigation("missing"), {
      wrapper: makeWrapper(queryClient),
    })
    expect(result.current).toEqual({
      prevId: null,
      nextId: null,
      prevTitle: null,
      nextTitle: null,
    })
  })

  it("handles cached entries missing a pages array gracefully", () => {
    const queryClient = freshClient()
    queryClient.setQueryData(["events", "list", { language: "ru" }], {})

    const { result } = renderHook(() => useEventNavigation("anything"), {
      wrapper: makeWrapper(queryClient),
    })
    expect(result.current.prevId).toBeNull()
    expect(result.current.nextId).toBeNull()
  })

  it("ignores cached pages that do not contain an items array", () => {
    const queryClient = freshClient()
    queryClient.setQueryData(["events", "list", { language: "ru" }], {
      pages: [{}, { items: [makeEvent("present")] }],
    })

    const { result } = renderHook(() => useEventNavigation("present"), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current).toEqual({
      prevId: null,
      nextId: null,
      prevTitle: null,
      nextTitle: null,
    })
  })
})
