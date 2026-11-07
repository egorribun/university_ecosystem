import {
  dehydrate,
  hydrate,
  QueryClient,
  QueryClientProvider,
  type InfiniteData,
} from "@tanstack/react-query"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { PaginatedNews } from "@/api/generated"
import type { NewsItem } from "@/api/news"
import { ApiResponseValidationError } from "@/api/validation"
import { useAuthStore } from "@/stores/useAuthStore"
import type { UserState } from "@/types/Auth"
import type { PaginatedResponse } from "@/types/Pagination"

const apiRequests = vi.hoisted(() => ({ authenticated: vi.fn() }))
vi.mock("@/api/generated/sdk.gen", () => ({
  newsListApiV1NewsGet: apiRequests.authenticated,
}))

import { anonymousNewsListQueryKey, newsListQueryKey, useNewsListQuery } from "../news"

const filters = { language: "en", limit: 12 }
const persistedItem = {
  id: "00000000-0000-4000-8000-000000000001",
  title: "Cached headline",
  content: "Cached article",
  created_at: "2026-01-15T10:00:00.000Z",
  image_url_optimized: null,
  likes_count: 0,
  comments_count: 0,
  is_liked: false,
} as NewsItem
const invalidPage = {
  items: [{ id: "not-a-uuid", title: "Malformed article" }],
  has_more: false,
  next_cursor: null,
}
const emptyBackendPage = {
  items: [],
  has_more: false,
} satisfies PaginatedNews
const page = <T,>(items: T[]): PaginatedResponse<T> => ({
  items,
  total: items.length,
  limit: 12,
  cursor: null,
  next_cursor: null,
  has_more: false,
})
const infinite = (items: NewsItem[]): InfiniteData<PaginatedResponse<NewsItem>, string | null> => ({
  pages: [page(items)],
  pageParams: [null],
})
const hydrateNewsData = (
  client: QueryClient,
  queryKey: ReturnType<typeof newsListQueryKey>,
  data: unknown
) => {
  const source = makeClient()
  source.setQueryData(queryKey, infinite([persistedItem]))
  const state = dehydrate(source)
  const query = state.queries.find(
    (entry) => JSON.stringify(entry.queryKey) === JSON.stringify(queryKey)
  )
  if (!query) throw new Error("Dehydrated news query was not created")
  query.state.data = data
  hydrate(client, state)
}

const hydrateNewsPage = (
  client: QueryClient,
  queryKey: ReturnType<typeof newsListQueryKey>,
  pageData: unknown
) => hydrateNewsData(client, queryKey, { pages: [pageData], pageParams: [null] })
const wrapperFor = (client: QueryClient) => {
  function QueryClientWrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
  return QueryClientWrapper
}
const makeClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })

beforeEach(() => {
  window.localStorage.clear()
  apiRequests.authenticated.mockReset()
  useAuthStore.setState({ user: { id: "feed-test-user" } as UserState, loading: false })
})

afterEach(() => {
  cleanup()
  window.localStorage.clear()
  useAuthStore.setState({ user: null, loading: true })
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("news list response validation", () => {
  it("rejects malformed authenticated news items and preserves the persisted snapshot", async () => {
    const key = "news:list:account:feed-test-user:en"
    const snapshot = [persistedItem]
    window.localStorage.setItem(key, JSON.stringify(snapshot))
    apiRequests.authenticated.mockResolvedValue({ status: 200, data: invalidPage })

    const client = makeClient()
    const { result } = renderHook(() => useNewsListQuery(filters), {
      wrapper: wrapperFor(client),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))

    expect(result.current.error).toBeInstanceOf(ApiResponseValidationError)
    expect(result.current.news).toEqual(snapshot)
    expect(window.localStorage.getItem(key)).toBe(JSON.stringify(snapshot))
    expect(client.getQueryState(newsListQueryKey(filters))?.status).toBe("error")
  })

  it("preserves the offline snapshot when an empty 2xx body is not a page", async () => {
    const key = "news:list:account:feed-test-user:en"
    const snapshot = [persistedItem]
    window.localStorage.setItem(key, JSON.stringify(snapshot))
    apiRequests.authenticated.mockResolvedValue({ status: 200, data: [] })

    const client = makeClient()
    const { result } = renderHook(() => useNewsListQuery(filters), {
      wrapper: wrapperFor(client),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))

    expect(result.current.error).toBeInstanceOf(ApiResponseValidationError)
    expect(result.current.news).toEqual(snapshot)
    expect(window.localStorage.getItem(key)).toBe(JSON.stringify(snapshot))
    expect(client.getQueryState(newsListQueryKey(filters))?.status).toBe("error")
  })

  it("ignores malformed persisted snapshots after an offline request failure", async () => {
    const key = "news:list:account:feed-test-user:en"
    const snapshot = [{ id: "not-a-uuid", title: "Malformed cached headline" }]
    window.localStorage.setItem(key, JSON.stringify(snapshot))
    apiRequests.authenticated.mockRejectedValue(new Error("network unavailable"))

    const client = makeClient()
    const { result } = renderHook(() => useNewsListQuery(filters), {
      wrapper: wrapperFor(client),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))

    expect(result.current.news).toEqual([])
    expect(result.current.isPlaceholderData).toBe(false)
    expect(window.localStorage.getItem(key)).toBe(JSON.stringify(snapshot))
    expect(client.getQueryState(newsListQueryKey(filters))?.status).toBe("error")
  })

  it("does not use an empty persisted snapshot as offline news", async () => {
    const key = "news:list:account:feed-test-user:en"
    window.localStorage.setItem(key, JSON.stringify([]))
    apiRequests.authenticated.mockRejectedValue(new Error("network unavailable"))

    const client = makeClient()
    const { result } = renderHook(() => useNewsListQuery(filters), {
      wrapper: wrapperFor(client),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))

    expect(result.current.news).toEqual([])
    expect(result.current.isPlaceholderData).toBe(false)
    expect(window.localStorage.getItem(key)).toBe("[]")
  })
  it("uses the validated offline snapshot instead of malformed hydrated articles", () => {
    const key = newsListQueryKey(filters)
    const snapshot = [persistedItem]
    window.localStorage.setItem("news:list:account:feed-test-user:en", JSON.stringify(snapshot))

    const client = makeClient()
    hydrateNewsPage(client, key, {
      items: [{ id: "not-a-uuid", title: "Malformed cached article" }],
      total: "invalid-total",
      limit: "invalid-limit",
      cursor: null,
      next_cursor: null,
      has_more: false,
    })

    const { result } = renderHook(() => useNewsListQuery(filters, { enabled: false }), {
      wrapper: wrapperFor(client),
    })

    expect(result.current.news).toEqual(snapshot)
    expect(result.current.pagination?.items).toEqual(snapshot)
    expect(window.localStorage.getItem("news:list:account:feed-test-user:en")).toBe(
      JSON.stringify(snapshot)
    )
  })

  it("uses the validated offline snapshot for a malformed hydrated page collection", () => {
    const key = newsListQueryKey(filters)
    const storageKey = "news:list:account:feed-test-user:en"
    const snapshot = [persistedItem]
    window.localStorage.setItem(storageKey, JSON.stringify(snapshot))

    const client = makeClient()
    hydrateNewsData(client, key, { pages: "malformed-pages", pageParams: [] })

    const { result } = renderHook(() => useNewsListQuery(filters, { enabled: false }), {
      wrapper: wrapperFor(client),
    })

    expect(result.current.news).toEqual(snapshot)
    expect(result.current.pagination?.items).toEqual(snapshot)
    expect(window.localStorage.getItem(storageKey)).toBe(JSON.stringify(snapshot))
  })
  it("keeps the validated offline snapshot when a malformed hydrated page gets a 304", async () => {
    const key = newsListQueryKey(filters)
    const snapshot = [persistedItem]
    const storageKey = "news:list:account:feed-test-user:en"
    window.localStorage.setItem(storageKey, JSON.stringify(snapshot))

    const client = makeClient()
    hydrateNewsPage(client, key, {
      items: "malformed-cache-items",
      total: "invalid-total",
      limit: "invalid-limit",
      cursor: null,
      next_cursor: null,
      has_more: false,
    })
    apiRequests.authenticated.mockResolvedValue({ status: 304, data: undefined })

    const { result } = renderHook(
      () => useNewsListQuery(filters, { enabled: false, staleTime: 0 }),
      { wrapper: wrapperFor(client) }
    )

    await act(async () => {
      await result.current.refetch()
    })

    expect(result.current.isSuccess).toBe(true)
    expect(result.current.news).toEqual(snapshot)
    expect(result.current.pagination?.items).toEqual(snapshot)
    expect(window.localStorage.getItem(storageKey)).toBe(JSON.stringify(snapshot))
  })

  it("normalizes malformed hydrated pagination metadata on a 304", async () => {
    const key = newsListQueryKey(filters)
    const client = makeClient()
    hydrateNewsPage(client, key, {
      items: [persistedItem],
      total: "invalid-total",
      limit: "invalid-limit",
      cursor: null,
      next_cursor: null,
      has_more: false,
    })
    apiRequests.authenticated.mockResolvedValue({ status: 304, data: undefined })

    const { result } = renderHook(
      () => useNewsListQuery(filters, { enabled: false, staleTime: 0 }),
      { wrapper: wrapperFor(client) }
    )

    await act(async () => {
      await result.current.refetch()
    })

    expect(result.current.pagination).toMatchObject({
      items: [persistedItem],
      total: 1,
      limit: 12,
      cursor: null,
      next_cursor: null,
      has_more: false,
    })
  })
  it("accepts a valid empty page in the backend wire shape for authenticated requests", async () => {
    apiRequests.authenticated.mockResolvedValue({
      status: 200,
      data: emptyBackendPage,
    })

    const client = makeClient()
    const { result } = renderHook(() => useNewsListQuery(filters), {
      wrapper: wrapperFor(client),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.news).toEqual([])
    expect(result.current.pagination).toMatchObject({
      items: [],
      total: 0,
      limit: 12,
      cursor: null,
      next_cursor: null,
      has_more: false,
    })
  })

  it("uses the requested limit and next cursor for a backend-shaped page", async () => {
    apiRequests.authenticated.mockResolvedValue({
      status: 200,
      data: {
        items: [persistedItem],
        has_more: true,
        next_cursor: "next-page",
      } satisfies PaginatedNews,
    })

    const client = makeClient()
    const { result } = renderHook(() => useNewsListQuery(filters), {
      wrapper: wrapperFor(client),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.pagination).toMatchObject({
      items: [{ id: persistedItem.id, likes_count: 0, comments_count: 0, is_liked: false }],
      total: 1,
      limit: 12,
      cursor: null,
      next_cursor: "next-page",
      has_more: true,
    })
  })

  it("rejects malformed anonymous news items and keeps the cached public page", async () => {
    const client = makeClient()
    const key = anonymousNewsListQueryKey(filters)
    const cached = infinite([persistedItem])
    client.setQueryData(key, cached)
    useAuthStore.setState({ user: null, loading: false })
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(invalidPage), { status: 200 }))
    )

    const { result } = renderHook(
      () => useNewsListQuery(filters, { enabled: false, staleTime: 0 }),
      { wrapper: wrapperFor(client) }
    )
    expect(result.current.queryKey).toEqual(key)

    await act(async () => {
      await result.current.refetch()
    })
    await waitFor(() => expect(result.current.isError).toBe(true))

    expect(result.current.error).toBeInstanceOf(ApiResponseValidationError)
    expect(result.current.news).toEqual([persistedItem])
    expect(client.getQueryData(key)).toEqual(cached)
    expect(client.getQueryCache().find({ queryKey: key })?.meta?.persist).toBe(false)
  })

  it("accepts a valid empty page in the backend wire shape for anonymous requests", async () => {
    const client = makeClient()
    const key = anonymousNewsListQueryKey(filters)
    useAuthStore.setState({ user: null, loading: false })
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(emptyBackendPage), { status: 200 }))
    )

    const { result } = renderHook(
      () => useNewsListQuery(filters, { enabled: false, staleTime: 0 }),
      { wrapper: wrapperFor(client) }
    )
    expect(result.current.queryKey).toEqual(key)

    await act(async () => {
      await result.current.refetch()
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.news).toEqual([])
    expect(result.current.pagination).toMatchObject({
      items: [],
      total: 0,
      limit: 12,
      cursor: null,
      next_cursor: null,
      has_more: false,
    })
    expect(apiRequests.authenticated).not.toHaveBeenCalled()
  })
})
