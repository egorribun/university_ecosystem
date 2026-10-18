import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import api from "@/api/client"
import { acceptBrowserSessionGeneration, invalidateSessionEpoch } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import type { UserState } from "@/types/Auth"
import { useNewsInteraction } from "../useNewsInteraction"

const id = "00000000-0000-0000-0000-000000000001"
const generationStorageKey = "ecosystem.session.generation.v1"
const accountKey = ["news", id, "interactions"] as const
const anonymousKey = ["news", id, "anonymous-interactions"] as const
const accountPages = {
  pages: [{ likes_count: 9, is_liked: true, comments: [], comments_count: 2 }],
  pageParams: [0],
}
const publicInteractions = {
  likes_count: 2,
  is_liked: false,
  comments: [],
  comments_count: 0,
}
const makeClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
const wrapperFor = (client: QueryClient) => {
  function QueryClientWrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }

  return QueryClientWrapper
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

beforeEach(() => {
  window.localStorage.clear()
  window.document.cookie = "session_cookie=; Max-Age=0; path=/"
  window.localStorage.setItem(
    generationStorageKey,
    JSON.stringify({ nonce: "generation-a", hash: "hash-a" })
  )
  acceptBrowserSessionGeneration()
  invalidateSessionEpoch()
  useAuthStore.setState({ user: { id: "account-a" } as UserState, loading: false })
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(publicInteractions), { status: 200 }))
  )
})

afterEach(() => {
  cleanup()
  useAuthStore.setState({ user: null, loading: true })
  window.localStorage.clear()
  window.document.cookie = "session_cookie=; Max-Age=0; path=/"
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("anonymous news interactions", () => {
  it("keeps stale account interaction state isolated and sends the read without successor cookies", async () => {
    const client = makeClient()
    client.setQueryData(accountKey, accountPages)
    window.document.cookie = "session_cookie=successor-account-b; path=/"
    publishGeneration("generation-b", "hash-b")
    const getSpy = vi.spyOn(api, "get")
    const { result } = renderHook(
      () =>
        useNewsInteraction(id, {
          initialData: { likes_count: 9, is_liked: true, comments_count: 2 },
          language: "en",
        }),
      { wrapper: wrapperFor(client) }
    )

    await waitFor(() => expect(result.current.interactions?.likes_count).toBe(2))
    expect(result.current.interactions?.is_liked).toBe(false)
    expect(result.current.interactions?.comments).toEqual([])
    expect(client.getQueryData(accountKey)).toEqual(accountPages)
    expect(client.getQueryCache().find({ queryKey: anonymousKey })?.meta?.persist).toBe(false)
    expect(getSpy).not.toHaveBeenCalled()

    const calls = vi.mocked(fetch).mock.calls
    expect(calls).toHaveLength(1)
    const call = calls[0]
    expect(call).toBeDefined()
    if (!call) throw new Error("anonymous interactions request missing")
    const url = new URL(String(call[0]), window.location.origin)
    expect(url.origin).toBe(window.location.origin)
    expect(url.pathname).toBe(`/api/v1/news/${id}/interactions`)
    expect(url.searchParams.get("limit")).toBe("20")
    expect(url.searchParams.get("offset")).toBe("0")
    expect(call[1]).toMatchObject({ credentials: "omit", cache: "no-store" })
    expect(new Headers(call[1]?.headers).get("Accept-Language")).toBe("en")
    expect(new Headers(call[1]?.headers).has("Cookie")).toBe(false)
    expect(new Headers(call[1]?.headers).has("Authorization")).toBe(false)
  })

  it("keeps like writes on the authenticated Axios mutation path", async () => {
    const postSpy = vi.spyOn(api, "post").mockResolvedValue({} as never)
    useAuthStore.setState({ user: null, loading: false })
    const client = makeClient()
    const { result } = renderHook(() => useNewsInteraction(id), {
      wrapper: wrapperFor(client),
    })

    await act(async () => {
      result.current.toggleLike()
    })
    await waitFor(() => expect(postSpy).toHaveBeenCalledWith(`/news/${id}/like`))
  })

  it("keeps an unavailable public interaction read out of the account cache", async () => {
    publishGeneration("generation-b", "hash-b")
    const client = makeClient()
    client.setQueryData(accountKey, accountPages)
    const fetchMock = vi.fn<typeof fetch>(async () => new Response("unavailable", { status: 503 }))
    vi.stubGlobal("fetch", fetchMock)
    const apiGet = vi.spyOn(api, "get")

    const { result } = renderHook(
      () =>
        useNewsInteraction(id, {
          initialData: { likes_count: 9, is_liked: true, comments_count: 2 },
          language: "en",
        }),
      { wrapper: wrapperFor(client) }
    )

    await waitFor(() =>
      expect(client.getQueryState(anonymousKey)?.error).toMatchObject({
        message: "News interactions request failed with status 503",
      })
    )
    expect(result.current.interactions?.is_liked).toBe(false)
    expect(client.getQueryData(accountKey)).toEqual(accountPages)
    expect(client.getQueryCache().find({ queryKey: anonymousKey })?.meta?.persist).toBe(false)
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(apiGet).not.toHaveBeenCalled()
  })
})
