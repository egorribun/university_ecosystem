import { onlineManager, QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { PropsWithChildren } from "react"

import type { NewsItem } from "@/api/news"
import {
  acceptBrowserSessionGeneration,
  hasStaleBrowserSessionBinding,
  invalidateSessionEpoch,
  rotateBrowserSession,
} from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import type { UserState } from "@/types/Auth"
import type { PaginatedResponse } from "@/types/Pagination"

const apiRequests = vi.hoisted(() => ({ news: vi.fn() }))
vi.mock("@/api/generated/sdk.gen", () => ({
  newsListApiV1NewsGet: apiRequests.news,
}))

import {
  anonymousNewsListQueryKey,
  newsDetailQueryOptions,
  newsListQueryKey,
  useAnonymousReadMode,
  useNewsListQuery,
} from "../news"

const generationStorageKey = "ecosystem.session.generation.v1"
const filters = { language: "en", limit: 12 }
const accountAKey = "news:list:account:account-a:en"
const accountBKey = "news:list:account:account-b:en"
const accountAItem = {
  id: "article-a",
  title: "Private A",
  is_liked: true,
} as NewsItem
const accountBItem = {
  id: "article-b",
  title: "Private B",
  is_liked: false,
} as NewsItem
const publicItem = {
  id: "article-public",
  title: "Public",
  is_liked: false,
} as NewsItem
const page = <T,>(items: T[]): PaginatedResponse<T> => ({
  items,
  total: items.length,
  limit: 12,
  cursor: null,
  next_cursor: null,
  has_more: false,
})
const infinite = (item: NewsItem) => ({
  pages: [page([item])],
  pageParams: [null],
})
const publicResponse = () =>
  ({ ok: true, status: 200, json: async () => page([publicItem]) }) as Response
const wrapperFor = (client: QueryClient) => {
  function QueryClientWrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }

  return QueryClientWrapper
}
const seedAccountA = () => {
  window.localStorage.setItem(
    generationStorageKey,
    JSON.stringify({ nonce: "generation-a", hash: "hash-a" })
  )
  acceptBrowserSessionGeneration()
  invalidateSessionEpoch()
  useAuthStore.setState({
    user: { id: "account-a" } as UserState,
    loading: false,
  })
}
const publishGeneration = (nonce: string, hash: string | null) => {
  const newValue = JSON.stringify({ nonce, hash })
  window.localStorage.setItem(generationStorageKey, newValue)
  window.dispatchEvent(
    new StorageEvent("storage", {
      key: generationStorageKey,
      newValue,
      storageArea: window.localStorage,
    })
  )
}
const makeClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  })

beforeEach(() => {
  window.localStorage.clear()
  window.document.cookie = "session_cookie=; Max-Age=0; path=/"
  apiRequests.news.mockReset()
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => publicResponse())
  )
  seedAccountA()
})

afterEach(() => {
  cleanup()
  useAuthStore.setState({ user: null, loading: true })
  window.localStorage.clear()
  window.document.cookie = "session_cookie=; Max-Age=0; path=/"
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("anonymous news during a stale cross-tab session", () => {
  it("uses a credentialless public key during logout-inflight without reading or replacing account A data", async () => {
    window.localStorage.setItem(accountAKey, JSON.stringify([accountAItem]))
    window.document.cookie = "session_cookie=old-account-a; path=/"
    expect(window.document.cookie).toContain("old-account-a")
    const client = makeClient()
    const authenticatedKey = newsListQueryKey(filters)
    const anonymousKey = anonymousNewsListQueryKey(filters)
    client.setQueryData(authenticatedKey, infinite(accountAItem))
    const fetchSpy = vi.mocked(fetch)
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useNewsListQuery(filters, { enabled }),
      { initialProps: { enabled: false }, wrapper: wrapperFor(client) }
    )
    expect(result.current.news).toEqual([accountAItem])

    const accountRead = vi.spyOn(Storage.prototype, "getItem")
    const accountWrite = vi.spyOn(Storage.prototype, "setItem")
    accountRead.mockClear()
    accountWrite.mockClear()
    act(() => publishGeneration("logout-inflight", null))
    await waitFor(() => expect(result.current.queryKey).toEqual(anonymousKey))
    expect(result.current.news).toEqual([])

    rerender({ enabled: true })
    await waitFor(() => expect(result.current.news).toEqual([publicItem]))

    expect(result.current.queryKey).toEqual(anonymousKey)
    expect(client.getQueryData(authenticatedKey)).toEqual(infinite(accountAItem))
    expect(client.getQueryData(anonymousKey)).toEqual({
      pages: [page([publicItem])],
      pageParams: [null],
    })
    expect(client.getQueryCache().find({ queryKey: anonymousKey })?.meta?.persist).toBe(false)
    expect(apiRequests.news).not.toHaveBeenCalled()
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(fetchSpy.mock.calls[0]?.[1]).toMatchObject({
      credentials: "omit",
      cache: "no-store",
    })
    expect(accountRead.mock.calls.filter(([key]) => key === accountAKey)).toEqual([])
    expect(accountWrite.mock.calls.filter(([key]) => key === accountAKey)).toEqual([])
    accountRead.mockRestore()
    accountWrite.mockRestore()
    expect(window.localStorage.getItem(accountAKey)).toBe(JSON.stringify([accountAItem]))
  })

  it("finishes a pending credentialless stale feed in only its anonymous cache after generation acceptance", async () => {
    apiRequests.news.mockResolvedValue({
      status: 200,
      data: page([accountAItem]),
    })
    let requestSignal: AbortSignal | undefined
    let resolvePublicResponse: ((response: Response) => void) | undefined
    const fetchSpy = vi.fn<typeof fetch>((_input, init) => {
      requestSignal = init?.signal ?? undefined
      return new Promise<Response>((resolve) => {
        resolvePublicResponse = resolve
      })
    })
    vi.stubGlobal("fetch", fetchSpy)
    window.localStorage.setItem(
      generationStorageKey,
      JSON.stringify({ nonce: "generation-b", hash: "hash-b" })
    )
    expect(hasStaleBrowserSessionBinding()).toBe(true)

    const client = makeClient()
    const authenticatedKey = newsListQueryKey(filters)
    const anonymousKey = anonymousNewsListQueryKey(filters)
    const { result, rerender } = renderHook(() => useNewsListQuery(filters), {
      wrapper: wrapperFor(client),
    })
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledOnce())
    expect(result.current.queryKey).toEqual(anonymousKey)
    expect(requestSignal?.aborted).toBe(false)

    acceptBrowserSessionGeneration()
    rerender()
    await waitFor(() => expect(result.current.queryKey).toEqual(authenticatedKey))
    expect(requestSignal?.aborted).toBe(false)
    await waitFor(() => expect(apiRequests.news).toHaveBeenCalledOnce())

    const resolve = resolvePublicResponse
    if (!resolve) throw new Error("public News feed request was not pending")
    resolve(
      new Response(JSON.stringify(page([publicItem])), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    )
    await waitFor(() => expect(client.getQueryData(anonymousKey)).toEqual(infinite(publicItem)))

    expect(client.getQueryData(authenticatedKey)).toEqual(infinite(accountAItem))
    expect(apiRequests.news).toHaveBeenCalledOnce()
  })

  it("uses the public cache and credentialless route when no account is confirmed", async () => {
    useAuthStore.setState({ user: null, loading: false })
    const client = makeClient()
    const anonymousKey = anonymousNewsListQueryKey(filters)

    const { result } = renderHook(() => useNewsListQuery(filters), {
      wrapper: wrapperFor(client),
    })
    await waitFor(() => expect(result.current.news).toEqual([publicItem]))

    expect(result.current.queryKey).toEqual(anonymousKey)
    expect(client.getQueryCache().find({ queryKey: anonymousKey })?.meta?.persist).toBe(false)
    expect(apiRequests.news).not.toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(vi.mocked(fetch).mock.calls[0]?.[1]).toMatchObject({
      credentials: "omit",
      cache: "no-store",
    })
  })

  it("does not send the successor account cookie or contaminate either account cache", async () => {
    window.localStorage.setItem(accountAKey, JSON.stringify([accountAItem]))
    window.localStorage.setItem(accountBKey, JSON.stringify([accountBItem]))
    window.document.cookie = "session_cookie=successor-account-b; path=/"
    expect(window.document.cookie).toContain("successor-account-b")
    const client = makeClient()
    const authenticatedKey = newsListQueryKey(filters)
    const anonymousKey = anonymousNewsListQueryKey(filters)
    client.setQueryData(authenticatedKey, infinite(accountAItem))

    const accountRead = vi.spyOn(Storage.prototype, "getItem")
    const accountWrite = vi.spyOn(Storage.prototype, "setItem")
    accountRead.mockClear()
    accountWrite.mockClear()
    publishGeneration("generation-b", "hash-b")

    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useNewsListQuery(filters, { enabled }),
      { initialProps: { enabled: false }, wrapper: wrapperFor(client) }
    )
    expect(result.current.queryKey).toEqual(anonymousKey)
    rerender({ enabled: true })
    await waitFor(() => expect(result.current.news).toEqual([publicItem]))

    expect(result.current.queryKey).toEqual(anonymousKey)
    expect(client.getQueryData(authenticatedKey)).toEqual(infinite(accountAItem))
    expect(client.getQueryData(anonymousKey)).toEqual({
      pages: [page([publicItem])],
      pageParams: [null],
    })
    expect(client.getQueryCache().find({ queryKey: anonymousKey })?.meta?.persist).toBe(false)
    expect(apiRequests.news).not.toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledTimes(1)
    const call = vi.mocked(fetch).mock.calls[0]
    expect(call?.[1]).toMatchObject({ credentials: "omit", cache: "no-store" })
    const headers = new Headers(call?.[1]?.headers)
    expect(headers.has("Cookie")).toBe(false)
    expect(headers.has("Authorization")).toBe(false)
    expect(
      accountRead.mock.calls.filter(([key]) => key === accountAKey || key === accountBKey)
    ).toEqual([])
    expect(
      accountWrite.mock.calls.filter(([key]) => key === accountAKey || key === accountBKey)
    ).toEqual([])
    accountRead.mockRestore()
    accountWrite.mockRestore()
    expect(window.localStorage.getItem(accountAKey)).toBe(JSON.stringify([accountAItem]))
    expect(window.localStorage.getItem(accountBKey)).toBe(JSON.stringify([accountBItem]))
  })
})

describe("news session-epoch fences", () => {
  it("hides an account snapshot when the browser generation changes during its scoped read", async () => {
    window.localStorage.setItem(accountAKey, JSON.stringify([accountAItem]))
    const client = makeClient()
    const accountKey = newsListQueryKey(filters)
    const anonymousKey = anonymousNewsListQueryKey(filters)
    client.setQueryData(accountKey, infinite(accountAItem))

    const nextGeneration = JSON.stringify({
      nonce: "generation-b",
      hash: "hash-b",
    })
    const originalGetItem = Storage.prototype.getItem
    const originalSetItem = Storage.prototype.setItem
    let published = false
    const storageRead = vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (
      this: Storage,
      key: string
    ) {
      const value = originalGetItem.call(this, key)
      if (!published && key === accountAKey) {
        published = true
        // Another tab can publish a new shared generation while this tab is
        // reading its owner-scoped offline snapshot, before the storage event
        // task updates the hook's anonymous-mode subscription.
        originalSetItem.call(this, generationStorageKey, nextGeneration)
      }
      return value
    })
    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
      this: Storage,
      key: string,
      value: string
    ) {
      return originalSetItem.call(this, key, value)
    })
    const exposedNewsIds: string[][] = []
    const selectedNewsIds: string[][] = []
    try {
      const { result } = renderHook(
        () => {
          const feed = useNewsListQuery(filters, { enabled: false })
          exposedNewsIds.push(feed.news.map((item) => item.id))
          selectedNewsIds.push(
            feed.data?.pages.flatMap((newsPage) => newsPage.items.map((item) => item.id)) ?? []
          )
          return feed
        },
        { wrapper: wrapperFor(client) }
      )

      expect(published).toBe(true)
      expect(hasStaleBrowserSessionBinding()).toBe(true)
      expect(result.current.news).toEqual([])
      expect(exposedNewsIds.every((ids) => !ids.includes(accountAItem.id))).toBe(true)
      expect(selectedNewsIds.every((ids) => !ids.includes(accountAItem.id))).toBe(true)
      expect(storageWrite.mock.calls.filter(([key]) => key === accountAKey)).toEqual([])

      act(() => {
        window.dispatchEvent(
          new StorageEvent("storage", {
            key: generationStorageKey,
            newValue: nextGeneration,
            storageArea: window.localStorage,
          })
        )
      })
      await waitFor(() => expect(result.current.queryKey).toEqual(anonymousKey))

      expect(result.current.news).toEqual([])
      expect(exposedNewsIds.every((ids) => !ids.includes(accountAItem.id))).toBe(true)
      expect(selectedNewsIds.every((ids) => !ids.includes(accountAItem.id))).toBe(true)
      expect(client.getQueryData(accountKey)).toEqual(infinite(accountAItem))
      expect(client.getQueryData(anonymousKey)).toBeUndefined()
      expect(window.localStorage.getItem(accountAKey)).toBe(JSON.stringify([accountAItem]))
      expect(storageWrite.mock.calls.filter(([key]) => key === accountAKey)).toEqual([])
      expect(apiRequests.news).not.toHaveBeenCalled()
      expect(fetch).not.toHaveBeenCalled()
    } finally {
      storageRead.mockRestore()
      storageWrite.mockRestore()
    }
  })
  it("rejects an inactive anonymous refetch after a failed rotation is accepted", async () => {
    publishGeneration("remote-generation", "remote-hash")
    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })
    rotateBrowserSession()
    storageWrite.mockRestore()
    expect(hasStaleBrowserSessionBinding()).toBe(true)

    const originalGetItem = Storage.prototype.getItem
    const storageRead = vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (
      this: Storage,
      key: string
    ) {
      if (key === generationStorageKey) throw new DOMException("blocked", "SecurityError")
      return originalGetItem.call(this, key)
    })
    const wasOnline = onlineManager.isOnline()
    onlineManager.setOnline(true)
    try {
      const client = makeClient()
      const anonymousKey = anonymousNewsListQueryKey(filters)
      const { result, rerender } = renderHook(
        ({ enabled }: { enabled: boolean }) => useNewsListQuery(filters, { enabled }),
        { initialProps: { enabled: true }, wrapper: wrapperFor(client) }
      )

      await waitFor(() => expect(result.current.news).toEqual([publicItem]))
      expect(result.current.queryKey).toEqual(anonymousKey)
      expect(hasStaleBrowserSessionBinding()).toBe(true)
      expect(fetch).toHaveBeenCalledTimes(1)
      expect(apiRequests.news).not.toHaveBeenCalled()

      // Keep the cached query successful and observed until after the session
      // fence changes. Moving a paused pending query would correctly cancel
      // and revert it before its captured query function could run.
      rerender({ enabled: false })
      acceptBrowserSessionGeneration()
      expect(hasStaleBrowserSessionBinding()).toBe(false)
      rerender({ enabled: false })
      expect(result.current.queryKey).toEqual(newsListQueryKey(filters))
      vi.mocked(fetch).mockClear()

      await expect(
        client.refetchQueries(
          { queryKey: anonymousKey, exact: true, type: "all" },
          { throwOnError: true }
        )
      ).rejects.toMatchObject({ name: "AbortError" })
      expect(client.getQueryState(anonymousKey)?.error?.name).toBe("AbortError")
      expect(client.getQueryData(anonymousKey)).toEqual({
        pages: [page([publicItem])],
        pageParams: [null],
      })
      expect(fetch).not.toHaveBeenCalled()
      expect(apiRequests.news).not.toHaveBeenCalled()
      expect(client.getQueryCache().find({ queryKey: anonymousKey })?.meta?.persist).toBe(false)
    } finally {
      onlineManager.setOnline(wasOnline)
      storageRead.mockRestore()
    }
  })

  it("hides a warm account list when its refresh loses the captured browser generation", async () => {
    const client = makeClient()
    const accountKey = newsListQueryKey(filters)
    client.setQueryData(accountKey, infinite(accountAItem), { updatedAt: 0 })
    let resolveResponse:
      ((value: { status: number; data: PaginatedResponse<NewsItem> }) => void) | undefined
    apiRequests.news.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveResponse = resolve
        })
    )

    const { result } = renderHook(() => useNewsListQuery(filters), {
      wrapper: wrapperFor(client),
    })
    await waitFor(() => expect(apiRequests.news).toHaveBeenCalledOnce())

    expect(result.current.news).toEqual([accountAItem])
    act(() => {
      // A different tab can publish the new generation before this tab handles
      // its storage event. The request must still reject its captured session.
      window.localStorage.setItem(
        generationStorageKey,
        JSON.stringify({ nonce: "generation-b", hash: "hash-b" })
      )
    })
    const resolve = resolveResponse
    if (!resolve) throw new Error("account news refresh was not pending")
    await act(async () => resolve({ status: 200, data: page([accountBItem]) }))

    await waitFor(() => {
      expect(client.getQueryState(accountKey)?.error?.name).toBe("AbortError")
      expect(result.current.queryKey).toEqual(anonymousNewsListQueryKey(filters))
      expect(result.current.news).toEqual([publicItem])
    })
    expect(client.getQueryData(accountKey)).toEqual(infinite(accountAItem))
    expect(client.getQueryData(anonymousNewsListQueryKey(filters))).toEqual({
      pages: [page([publicItem])],
      pageParams: [null],
    })
    expect(
      client.getQueryCache().find({ queryKey: anonymousNewsListQueryKey(filters) })?.meta?.persist
    ).toBe(false)
    expect(apiRequests.news).toHaveBeenCalledOnce()
    expect(fetch).toHaveBeenCalledTimes(1)
    const anonymousCall = vi.mocked(fetch).mock.calls[0]
    expect(anonymousCall?.[1]).toMatchObject({
      credentials: "omit",
      cache: "no-store",
    })
    expect(new Headers(anonymousCall?.[1]?.headers).has("Cookie")).toBe(false)
    expect(new Headers(anonymousCall?.[1]?.headers).has("Authorization")).toBe(false)
  })
})

describe("anonymous news detail session isolation", () => {
  const id = "00000000-0000-0000-0000-000000000001"
  const accountDetail = {
    id,
    title: "Account A article",
    content: "Private account interaction state",
    created_at: "2026-10-18T00:00:00Z",
    image_url_optimized: null,
    likes_count: 19,
    comments_count: 4,
    is_liked: true,
  } as NewsItem
  const publicDetail = {
    id,
    title: "Public article",
    content: "Public body",
    created_at: "2026-10-18T00:00:00Z",
    image_url_optimized: null,
    likes_count: 2,
    comments_count: 1,
    is_liked: false,
  } as NewsItem

  it("selects a credentialless detail key after a stale session and preserves the account cache", async () => {
    const accountKey = ["news", id, "en"] as const
    const client = makeClient()
    client.setQueryData(accountKey, accountDetail)
    publishGeneration("logout-inflight-detail", null)
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(publicDetail), { status: 200 }))
    )

    const { result } = renderHook(
      () => {
        const { anonymous } = useAnonymousReadMode()
        return useQuery(newsDetailQueryOptions(id, "en", anonymous))
      },
      { wrapper: wrapperFor(client) }
    )
    await waitFor(() => expect(result.current.data?.title).toBe("Public article"))

    const anonymousKey = ["news", "anonymous-detail", id, "en"] as const
    expect(result.current.data?.is_liked).toBe(false)
    expect(result.current.data?.likes_count).toBe(2)
    expect(client.getQueryData(accountKey)).toEqual(accountDetail)
    expect(client.getQueryData(anonymousKey)).toEqual(publicDetail)
    expect(client.getQueryCache().find({ queryKey: anonymousKey })?.meta?.persist).toBe(false)
    expect(fetch).toHaveBeenCalledTimes(1)
    const call = vi.mocked(fetch).mock.calls[0]
    expect(call?.[0]).toBeInstanceOf(URL)
    expect(String(call?.[0])).toBe(`${window.location.origin}/api/v1/news/${id}`)
    expect(call?.[1]).toMatchObject({ credentials: "omit", cache: "no-store" })
    expect(new Headers(call?.[1]?.headers).has("Cookie")).toBe(false)
    expect(new Headers(call?.[1]?.headers).has("Authorization")).toBe(false)
    expect(apiRequests.news).not.toHaveBeenCalled()
  })
})
