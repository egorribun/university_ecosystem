import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, renderHook } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { useRelatedNews } from "../useRelatedNews"
import { useRelatedEvents } from "../useRelatedEvents"

beforeEach(() => {
  localStorage.clear()
  acceptBrowserSessionGeneration()
})
afterEach(() => {
  cleanup()
  localStorage.clear()
  acceptBrowserSessionGeneration()
  vi.restoreAllMocks()
})

// Both hooks return items with a title; the shared shape keeps renderHook monomorphic.
const cases: ReadonlyArray<{
  root: "news" | "events"
  useItems: () => ReadonlyArray<{ title: string }>
}> = [
  { root: "news", useItems: () => useRelatedNews("current", "education") },
  { root: "events", useItems: () => useRelatedEvents("current", "lecture") },
]

describe.each(cases)("related $root cache subscription", ({ root, useItems }) => {
  const key = [root, "list", "account-a"]
  const page = (title: string) => ({
    pages: [{ items: [{ id: "related", title, content: "study exam", event_type: "lecture" }] }],
    pageParams: [null],
  })

  function setup() {
    const client = new QueryClient({ defaultOptions: { queries: { gcTime: Infinity } } })
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    )
    return { client, wrapper }
  }

  it("reacts to insertion, replacement and removal without a parent rerender", () => {
    const { client, wrapper } = setup()
    const { result, unmount } = renderHook(useItems, { wrapper })
    expect(result.current).toEqual([])
    act(() => client.setQueryData(key, page("First")))
    expect(result.current.map((item) => item.title)).toEqual(["First"])
    act(() => client.setQueryData(key, page("Updated")))
    expect(result.current.map((item) => item.title)).toEqual(["Updated"])
    act(() => client.removeQueries({ queryKey: key }))
    expect(result.current).toEqual([])
    unmount()
    client.clear()
  })

  it("keeps a stable snapshot for unrelated queries and data-preserving notifications", async () => {
    const { client, wrapper } = setup()
    client.setQueryData(key, page("First"))
    let renders = 0
    const { result, unmount } = renderHook(
      () => {
        renders += 1
        return useItems()
      },
      { wrapper }
    )
    const initial = result.current
    const initialRenders = renders
    await act(async () => {
      client.setQueryData(["unrelated"], { value: 1 })
      await client.invalidateQueries({ queryKey: key, refetchType: "none" })
    })
    expect(result.current).toBe(initial)
    expect(renders).toBe(initialRenders)
    unmount()
    client.clear()
  })

  it("hides old session data on a storage transition and refuses later cache updates", async () => {
    const { client, wrapper } = setup()
    client.setQueryData(key, page("Private A"))
    const { result, unmount } = renderHook(useItems, { wrapper })
    expect(result.current).toHaveLength(1)
    await act(async () => {
      localStorage.setItem(
        "ecosystem.session.generation.v1",
        JSON.stringify({
          nonce: "other-tab-generation",
          hash: "other-account-hash",
        })
      )
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: "ecosystem.session.generation.v1",
        })
      )
    })
    expect(result.current).toEqual([])
    act(() => client.setQueryData(key, page("Late private A")))
    expect(result.current).toEqual([])
    unmount()
    client.clear()
  })

  it("keeps snapshots isolated between QueryClient providers", () => {
    const first = setup()
    const second = setup()
    first.client.setQueryData(key, page("First provider"))
    second.client.setQueryData(key, page("Second provider"))
    const firstView = renderHook(useItems, { wrapper: first.wrapper })
    const secondView = renderHook(useItems, { wrapper: second.wrapper })

    expect(firstView.result.current.map((item) => item.title)).toEqual(["First provider"])
    expect(secondView.result.current.map((item) => item.title)).toEqual(["Second provider"])
    act(() => first.client.setQueryData(key, page("Updated first")))
    expect(firstView.result.current.map((item) => item.title)).toEqual(["Updated first"])
    expect(secondView.result.current.map((item) => item.title)).toEqual(["Second provider"])

    firstView.unmount()
    secondView.unmount()
    first.client.clear()
    second.client.clear()
  })

  it("unsubscribes from the query cache on unmount", () => {
    const { client, wrapper } = setup()
    const cache = client.getQueryCache()
    const subscribe = cache.subscribe.bind(cache)
    const unsubscribe = vi.fn()
    vi.spyOn(cache, "subscribe").mockImplementation((listener) => {
      const stop = subscribe(listener)
      return () => {
        unsubscribe()
        stop()
      }
    })
    const { unmount } = renderHook(useItems, { wrapper })
    unmount()
    expect(unsubscribe).toHaveBeenCalledOnce()
    client.clear()
  })
})
