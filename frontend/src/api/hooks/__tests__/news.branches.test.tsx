/**
 * @fileoverview Wave session-15 branch top-up for `src/api/hooks/news.ts`.
 *
 * The `ssrFactories.test.ts` sibling already covers the detail/prefetch
 * factory SHAPES (queryKey / staleTime / getNextPageParam). This file targets
 * the UNCOVERED runtime closures + branches:
 *
 *   - newsListQueryKey() factory (95-97)
 *   - ensurePaginatedResponse() null-payload fallback (104-112)
 *   - mergeNewsPages() last-write-wins dedupe across pages (140)
 *   - createNewsListQueryFn cursor-param branch (159-160) + 304 fallback (174-177)
 *   - useNewsListQuery placeholderData offline-success path (255-270)
 *   - fetchNewsDetail 304 / no-data / success branches (348-352)
 *
 * NEVER hits MSW for /api paths (contract validator rejects off-schema
 * responses): the generated SDK + `@/api/news` modules are vi.mock'd so the
 * queryFn closures see controlled responses.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { NewsItem } from "@/api/news"
import { StorageItem } from "@/utils/storage"

// ── SDK + @/api/news mock ─────────────────────────────────────────────────────
// useNewsListQuery imports `newsListApiV1NewsGet` statically; newsDetailQueryOptions
// goes through `fetchNewsItem` from "@/api/news".
const newsListMock = vi.fn<(...args: unknown[]) => Promise<unknown>>()
const fetchNewsItemMock = vi.fn<(...args: unknown[]) => Promise<unknown>>()

vi.mock("@/api/generated/sdk.gen", () => ({
  newsListApiV1NewsGet: (...args: unknown[]) => newsListMock(...args),
}))

vi.mock("@/api/news", () => ({
  fetchNewsItem: (...args: unknown[]) => fetchNewsItemMock(...args),
}))

import {
  newsListQueryKey,
  prefetchNewsListQuery,
  useNewsListQuery,
  newsDetailQueryOptions,
} from "@/api/hooks/news"

const makeNews = (id: string, title = `News ${id}`): NewsItem =>
  ({
    id,
    title,
    created_at: "2026-01-15T10:00:00.000Z",
  }) as unknown as NewsItem

const okPage = (items: NewsItem[], next_cursor: string | null = null) => ({
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
  newsListMock.mockReset()
  fetchNewsItemMock.mockReset()
  if (typeof window !== "undefined") window.localStorage.clear()
})

afterEach(() => {
  if (typeof window !== "undefined") window.localStorage.clear()
})

// ── newsListQueryKey factory (news.ts:95-97) ──────────────────────────────────
describe("newsListQueryKey (news.ts:95-97)", () => {
  it("normalizes filters into ['news', 'list', normalized] with default limit", () => {
    const key = newsListQueryKey({ language: "ru" })
    expect(key[0]).toBe("news")
    expect(key[1]).toBe("list")
    expect(key[2]).toEqual({ language: "ru", limit: 12 })
  })

  it("floors a fractional limit and shares cache with undefined limit when defaulted", () => {
    expect(newsListQueryKey({ language: "en", limit: 20.9 })[2].limit).toBe(20)
    // undefined + explicit page-size collapse to the same normalized key
    expect(newsListQueryKey({ language: "en", limit: undefined })).toEqual(
      newsListQueryKey({ language: "en", limit: 12 })
    )
  })

  it("falls back to page size for non-positive / non-finite limit", () => {
    expect(newsListQueryKey({ language: "ru", limit: 0 })[2].limit).toBe(12)
    expect(newsListQueryKey({ language: "ru", limit: -3 })[2].limit).toBe(12)
    expect(newsListQueryKey({ language: "ru", limit: Number.NaN })[2].limit).toBe(12)
    expect(newsListQueryKey({ language: "ru", limit: Number.POSITIVE_INFINITY })[2].limit).toBe(12)
    expect(newsListQueryKey({ language: "ru", limit: Number.NEGATIVE_INFINITY })[2].limit).toBe(12)
    // Runtime callers can still provide null through decoded query params;
    // treat it exactly like an omitted/invalid page size.
    expect(newsListQueryKey({ language: "ru", limit: null as unknown as number })[2].limit).toBe(12)
  })

  it("keeps a valid explicit limit distinct from every invalid boundary", () => {
    expect(newsListQueryKey({ language: "ru", limit: 1 })[2].limit).toBe(1)
    expect(newsListQueryKey({ language: "ru", limit: undefined })[2].limit).toBe(12)
  })

  it("exposes the canonical key from the hook", () => {
    const queryClient = freshClient()
    const { result } = renderHook(
      () => useNewsListQuery({ language: "en", limit: 20.9 }, { enabled: false }),
      { wrapper: makeWrapper(queryClient) }
    )

    expect(result.current.queryKey).toEqual(["news", "list", { language: "en", limit: 20 }])
  })
})

// ── useNewsListQuery queryFn: null fallback (104-112) + cursor (159-160) + 304 ─
describe("useNewsListQuery queryFn branches", () => {
  it("ensurePaginatedResponse fallback when response.data is null (news.ts:104-112)", async () => {
    newsListMock.mockResolvedValue({ status: 200, data: null })

    const queryClient = freshClient()
    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.news).toEqual([])
    expect(newsListMock.mock.calls[0]?.[0]).toEqual(expect.objectContaining({ throwOnError: true }))
    expect(result.current.pagination).toEqual({
      items: [],
      total: 0,
      limit: 12,
      cursor: null,
      next_cursor: null,
      has_more: false,
    })
  })

  it("preserves valid pagination fields and sends the complete first-page contract", async () => {
    const item = makeNews("numeric-fields")
    newsListMock.mockResolvedValue({
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
    const { result } = renderHook(() => useNewsListQuery({ language: "ru", limit: 5 }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.pagination).toMatchObject({
      items: [item],
      total: 99,
      limit: 7,
      cursor: "server-cursor",
      next_cursor: null,
      has_more: false,
    })

    const request = newsListMock.mock.calls[0]?.[0] as {
      query?: Record<string, unknown>
      etagCacheKey?: string
      validateStatus?: (status: number) => boolean
    }
    expect(request.query).toEqual({ limit: 5 })
    expect(request).toHaveProperty("throwOnError", true)
    expect(request.etagCacheKey).toBe("news:list:ru:5")
    expect(request.validateStatus?.(199)).toBe(false)
    expect(request.validateStatus?.(200)).toBe(true)
    expect(request.validateStatus?.(399)).toBe(true)
    expect(request.validateStatus?.(400)).toBe(false)
  })

  it("passes cursor param on fetchNextPage (news.ts:158-160)", async () => {
    const firstPage = [makeNews("a"), makeNews("b")]
    const secondPage = [makeNews("c")]
    newsListMock
      .mockResolvedValueOnce(okPage(firstPage, "cursor-2"))
      .mockResolvedValueOnce(okPage(secondPage, null))

    const queryClient = freshClient()
    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.news).toHaveLength(2))
    expect(result.current.hasNextPage).toBe(true)

    await act(async () => {
      await result.current.fetchNextPage()
    })

    await waitFor(() => expect(result.current.news).toHaveLength(3))
    const secondCall = newsListMock.mock.calls[1]?.[0] as { query?: Record<string, unknown> }
    expect(secondCall?.query?.cursor).toBe("cursor-2")
  })

  it("reports null pagination while an uncached request is pending", async () => {
    let resolveRequest: (value: unknown) => void = () => {}
    newsListMock.mockImplementation(
      () =>
        new Promise<unknown>((resolve) => {
          resolveRequest = resolve
        })
    )

    const queryClient = freshClient()
    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isPending).toBe(true))
    expect(result.current.pagination).toBeNull()
    await act(async () => resolveRequest(okPage([], null)))
  })

  it("uses ETag only for the first page and carries the cursor on later pages", async () => {
    newsListMock
      .mockResolvedValueOnce(okPage([makeNews("etag-first")], "cursor-2"))
      .mockResolvedValueOnce(okPage([makeNews("etag-second")], null))

    const queryClient = freshClient()
    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.hasNextPage).toBe(true))
    const firstCall = newsListMock.mock.calls[0]?.[0] as {
      query?: Record<string, unknown>
      etagCacheKey?: string
    }
    expect(firstCall.query).not.toHaveProperty("cursor")
    expect(firstCall.etagCacheKey).toBe("news:list:ru:12")

    await act(async () => {
      await result.current.fetchNextPage()
    })
    await waitFor(() => expect(result.current.news).toHaveLength(2))

    const secondCall = newsListMock.mock.calls[1]?.[0] as {
      query?: Record<string, unknown>
      etagCacheKey?: string
    }
    expect(secondCall.query).toEqual({ limit: 12, cursor: "cursor-2" })
    expect(secondCall).not.toHaveProperty("etagCacheKey")
  })

  it("304 response falls back to cached first page (news.ts:173-177)", async () => {
    const cachedItems = [makeNews("z1"), makeNews("z2")]
    newsListMock
      .mockResolvedValueOnce(okPage(cachedItems, null))
      .mockResolvedValueOnce({ status: 304, data: undefined })

    const queryClient = freshClient()
    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.news).toHaveLength(2))

    await act(async () => {
      await result.current.refetch()
    })

    await waitFor(() => expect(result.current.isFetching).toBe(false))
    expect(result.current.news).toHaveLength(2)
  })

  it("304 response restores the persisted page when the query cache is cold", async () => {
    const persistedItems = [makeNews("persisted-1"), makeNews("persisted-2")]
    window.localStorage.setItem("news:list:ru", JSON.stringify(persistedItems))
    newsListMock.mockResolvedValue({ status: 304, data: undefined })

    const queryClient = freshClient()
    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(newsListMock).toHaveBeenCalledOnce())
    await waitFor(() => expect(result.current.isFetching).toBe(false))
    expect(result.current.news).toEqual(persistedItems)
  })

  it("304 response with a malformed or cold cache safely returns an empty page", async () => {
    newsListMock.mockResolvedValue({ status: 304, data: undefined })

    const queryClient = freshClient()
    // With no cached infinite-query entry the optional pages chain must treat
    // the 304 as a cache miss, not dereference an undefined cache value.
    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.news).toEqual([])
    expect(result.current.pagination).toEqual({
      items: [],
      total: 0,
      limit: 12,
      cursor: null,
      next_cursor: null,
      has_more: false,
    })
  })

  it("304 response tolerates a cached entry without a pages array", async () => {
    newsListMock.mockResolvedValue({ status: 304, data: undefined })

    const queryClient = freshClient()
    vi.spyOn(queryClient, "getQueryData").mockReturnValue({
      pages: undefined,
    } as never)

    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.news).toEqual([])
    expect(result.current.pagination).toEqual({
      items: [],
      total: 0,
      limit: 12,
      cursor: null,
      next_cursor: null,
      has_more: false,
    })
  })

  it("returns null pagination for an empty in-memory infinite-data entry", () => {
    const queryClient = freshClient()
    queryClient.setQueryData(newsListQueryKey({ language: "ru" }), {
      pages: [],
      pageParams: [],
    })

    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }, { enabled: false }), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.pagination).toBeNull()
    expect(result.current.news).toEqual([])
  })

  it("normalizes malformed pagination fields to safe defaults", async () => {
    newsListMock.mockResolvedValue({
      status: 200,
      data: { items: "invalid", total: "invalid", limit: "invalid" },
    })
    const queryClient = freshClient()
    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.news).toEqual([])
    expect(result.current.pagination?.total).toBe(0)
    expect(result.current.pagination?.limit).toBe(12)
  })
})

// ── mergeNewsPages last-write-wins dedupe (news.ts:140) ───────────────────────
describe("mergeNewsPages dedupe (news.ts:140 via shared id across pages)", () => {
  it("later page overwrites the earlier item with the same id", async () => {
    const page1 = [makeNews("dup", "OLD"), makeNews("solo")]
    const page2 = [makeNews("dup", "NEW")]
    newsListMock
      .mockResolvedValueOnce(okPage(page1, "next"))
      .mockResolvedValueOnce(okPage(page2, null))

    const queryClient = freshClient()
    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.news).toHaveLength(2))
    await act(async () => {
      await result.current.fetchNextPage()
    })
    await waitFor(() => expect(result.current.news).toHaveLength(2))

    const dup = result.current.news.find((n) => n.id === "dup")
    expect(dup?.title).toBe("NEW")
  })
})

// ── useNewsListQuery placeholderData offline-success path (news.ts:255-270) ───
describe("useNewsListQuery placeholderData offline (news.ts:255-270)", () => {
  it("persists a successful news response for a later offline mount", async () => {
    const received = [makeNews("cached-1"), makeNews("cached-2")]
    newsListMock.mockResolvedValue(okPage(received, null))

    const queryClient = freshClient()
    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    await waitFor(() =>
      expect(window.localStorage.getItem("news:list:ru")).toBe(JSON.stringify(received))
    )
  })

  it("seeds news from localStorage when no network response yet", async () => {
    const stored = [makeNews("p1"), makeNews("p2")]
    // key shape: news:list:<language>
    window.localStorage.setItem("news:list:ru", JSON.stringify(stored))

    let resolveFn: (v: unknown) => void = () => {}
    newsListMock.mockImplementation(
      () => new Promise((resolve) => (resolveFn = resolve as (v: unknown) => void))
    )

    const queryClient = freshClient()
    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.news).toEqual(stored))
    expect(result.current.pagination).toMatchObject({
      total: 2,
      limit: 12,
      has_more: false,
    })

    await act(async () => {
      resolveFn(okPage(stored, null))
    })
  })

  it("keeps the persisted feed visible when an SSR-hydrated query fails offline", async () => {
    const stored = [makeNews("offline-1"), makeNews("offline-2")]
    window.localStorage.setItem("news:list:ru", JSON.stringify(stored))
    newsListMock.mockRejectedValue(new Error("offline"))

    const queryClient = freshClient()
    queryClient.setQueryData(newsListQueryKey({ language: "ru" }), {
      pages: [],
      pageParams: [],
    })
    const { result } = renderHook(
      () => useNewsListQuery({ language: "ru", limit: 12 }, { staleTime: 0 }),
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.news).toEqual(stored)
  })

  it("returns an empty feed when an offline error has no persisted snapshot", async () => {
    newsListMock.mockRejectedValue(new Error("offline"))

    const queryClient = freshClient()
    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.news).toEqual([])
  })

  it("returns no placeholder when stored items are empty/missing", async () => {
    window.localStorage.setItem("news:list:ru", JSON.stringify([]))
    newsListMock.mockResolvedValue(okPage([], null))

    const queryClient = freshClient()
    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })
    expect(result.current.news).toEqual([])
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })

  it("does not create a placeholder page for an empty persisted snapshot", async () => {
    window.localStorage.setItem("news:list:ru", JSON.stringify([]))
    let resolveFn: (value: unknown) => void = () => {}
    newsListMock.mockImplementation(
      () => new Promise((resolve) => (resolveFn = resolve as (value: unknown) => void))
    )

    const queryClient = freshClient()
    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isPending).toBe(true))
    expect(result.current.pagination).toBeNull()
    expect(result.current.news).toEqual([])

    await act(async () => {
      resolveFn(okPage([], null))
    })
  })

  it("placeholder swallows malformed JSON gracefully (news.ts:268-269)", async () => {
    window.localStorage.setItem("news:list:ru", "{not-json")
    newsListMock.mockResolvedValue(okPage([], null))

    const queryClient = freshClient()
    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })
    expect(result.current.news).toEqual([])
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })

  it("keeps live data visible when a refetch fails", async () => {
    const live = [makeNews("live")]
    newsListMock
      .mockResolvedValueOnce(okPage(live, null))
      .mockRejectedValueOnce(new Error("offline"))

    const queryClient = freshClient()
    const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    await act(async () => {
      await result.current.refetch()
    })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.news).toEqual(live)
  })

  it("does not persist a placeholder before the network resolves", async () => {
    const stored = [makeNews("placeholder")]
    window.localStorage.setItem("news:list:ru", JSON.stringify(stored))
    let resolveRequest: (value: unknown) => void = () => {}
    newsListMock.mockImplementation(
      () =>
        new Promise<unknown>((resolve) => {
          resolveRequest = resolve
        })
    )
    const setSpy = vi.spyOn(StorageItem.prototype, "set").mockImplementation(() => true)

    try {
      const queryClient = freshClient()
      const { result } = renderHook(() => useNewsListQuery({ language: "ru" }), {
        wrapper: makeWrapper(queryClient),
      })

      await waitFor(() => expect(result.current.news).toEqual(stored))
      expect(setSpy).not.toHaveBeenCalled()
      await act(async () => resolveRequest(okPage(stored, null)))
    } finally {
      setSpy.mockRestore()
    }
  })

  it("refreshes the persisted snapshot and key when language or limit changes", () => {
    window.localStorage.setItem("news:list:ru", JSON.stringify([makeNews("ru")]))
    window.localStorage.setItem("news:list:en", JSON.stringify([makeNews("en")]))
    const queryClient = freshClient()
    const { result, rerender } = renderHook(
      ({ language, limit }: { language: string; limit: number }) =>
        useNewsListQuery({ language, limit }, { enabled: false }),
      {
        initialProps: { language: "ru", limit: 12 },
        wrapper: makeWrapper(queryClient),
      }
    )

    expect(result.current.queryKey).toEqual(["news", "list", { language: "ru", limit: 12 }])
    expect(result.current.news.map((item) => item.id)).toEqual(["ru"])
    rerender({ language: "en", limit: 20 })
    expect(result.current.queryKey).toEqual(["news", "list", { language: "en", limit: 20 }])
    expect(result.current.news.map((item) => item.id)).toEqual(["en"])
  })
})

describe("prefetchNewsListQuery pagination contract", () => {
  it("uses the canonical key and treats missing pages as terminal", async () => {
    newsListMock.mockResolvedValue(okPage([], null))
    const queryClient = freshClient()
    const prefetchSpy = vi.spyOn(queryClient, "prefetchInfiniteQuery")

    await prefetchNewsListQuery(queryClient, { language: "en", limit: 12 })

    expect(prefetchSpy).toHaveBeenCalledOnce()
    const options = prefetchSpy.mock.calls[0]?.[0] as unknown as {
      queryKey: unknown
      getNextPageParam: (...args: unknown[]) => unknown
    }
    expect(options.queryKey).toEqual(["news", "list", { language: "en", limit: 12 }])
    expect(options.getNextPageParam(undefined)).toBeNull()
    expect(options.getNextPageParam({ next_cursor: "next" })).toBe("next")
  })
})

// ── fetchNewsDetail via newsDetailQueryOptions.queryFn (news.ts:348-352) ──────
describe("newsDetailQueryOptions.queryFn → fetchNewsDetail (news.ts:347-352)", () => {
  it("returns response.data on a successful (non-304, data present) fetch", async () => {
    const item = makeNews("nd-1", "Detail body")
    fetchNewsItemMock.mockResolvedValue({ status: 200, data: item })

    const opts = newsDetailQueryOptions("nd-1", "ru")
    const out = await opts.queryFn({ signal: undefined })

    expect(out).toEqual(item)
    expect(fetchNewsItemMock).toHaveBeenCalledWith(
      "nd-1",
      expect.objectContaining({ signal: undefined })
    )
  })

  it("throws 'Not modified' on a 304 response (news.ts:349)", async () => {
    fetchNewsItemMock.mockResolvedValue({ status: 304, data: undefined })
    const opts = newsDetailQueryOptions("nd-2", "en")
    await expect(opts.queryFn({ signal: undefined })).rejects.toThrow("Not modified")
  })

  it("throws 'Item not found' when 200 but no data (news.ts:350)", async () => {
    fetchNewsItemMock.mockResolvedValue({ status: 200, data: null })
    const opts = newsDetailQueryOptions("nd-3", "ru")
    await expect(opts.queryFn({ signal: undefined })).rejects.toThrow("Item not found")
  })

  it("propagates the AbortSignal through to fetchNewsItem", async () => {
    const item = makeNews("nd-4")
    fetchNewsItemMock.mockResolvedValue({ status: 200, data: item })
    const controller = new AbortController()

    const opts = newsDetailQueryOptions("nd-4", "ru")
    await opts.queryFn({ signal: controller.signal })

    expect(fetchNewsItemMock).toHaveBeenCalledWith(
      "nd-4",
      expect.objectContaining({ signal: controller.signal })
    )
  })
})
