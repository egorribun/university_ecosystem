import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { StoryItem } from "@/types/Story"

const fetchStoriesMock = vi.hoisted(() => vi.fn())

vi.mock("@/api/stories", () => ({
  fetchStories: (...args: unknown[]) => fetchStoriesMock(...args),
}))

import {
  createDashboardStoriesQueryOptions,
  dashboardStoriesQueryKey,
  prefetchDashboardStories,
  useDashboardStories,
} from "@/hooks/useDashboardStories"

const story = { id: "story-1", title: "Campus" } as StoryItem

const runQuery = async (queryClient: QueryClient, signal?: AbortSignal): Promise<StoryItem[]> => {
  const options = createDashboardStoriesQueryOptions(queryClient)
  return await options.queryFn({
    queryKey: dashboardStoriesQueryKey,
    pageParam: undefined,
    signal: signal ?? new AbortController().signal,
    client: queryClient,
    meta: undefined,
  })
}

beforeEach(() => {
  fetchStoriesMock.mockReset()
})

describe("useDashboardStories query closure", () => {
  it("filters falsey payload entries and handles a non-array payload", async () => {
    const queryClient = new QueryClient()
    fetchStoriesMock.mockResolvedValueOnce({ data: [story, null, false] })
    await expect(runQuery(queryClient)).resolves.toEqual([story])

    fetchStoriesMock.mockResolvedValueOnce({ data: { unexpected: true } })
    await expect(runQuery(queryClient)).resolves.toEqual([])
  })

  it("returns the cached snapshot for 304 and an empty list without a snapshot", async () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(dashboardStoriesQueryKey, [story])
    fetchStoriesMock.mockResolvedValueOnce({ status: 304, data: undefined })
    await expect(runQuery(queryClient)).resolves.toEqual([story])

    const emptyClient = new QueryClient()
    fetchStoriesMock.mockResolvedValueOnce({ status: 304, data: undefined })
    await expect(runQuery(emptyClient)).resolves.toEqual([])
  })

  it("falls back to cached data on a non-abort error and rethrows otherwise", async () => {
    const cachedClient = new QueryClient()
    cachedClient.setQueryData(dashboardStoriesQueryKey, [story])
    const recoverable = new Error("temporary failure")
    fetchStoriesMock.mockRejectedValueOnce(recoverable)
    await expect(runQuery(cachedClient)).resolves.toEqual([story])

    const aborted = new Error("aborted")
    const controller = new AbortController()
    controller.abort()
    fetchStoriesMock.mockRejectedValueOnce(aborted)
    await expect(runQuery(new QueryClient(), controller.signal)).rejects.toBe(aborted)

    const terminal = new Error("terminal failure")
    fetchStoriesMock.mockRejectedValueOnce(terminal)
    await expect(runQuery(new QueryClient())).rejects.toBe(terminal)
  })

  it("preserves placeholder semantics and delegates prefetch", async () => {
    const queryClient = new QueryClient()
    const options = createDashboardStoriesQueryOptions(queryClient)
    expect(options.placeholderData(undefined)).toEqual([])
    expect(options.placeholderData([story])).toEqual([story])

    const prefetch = vi.spyOn(queryClient, "prefetchQuery").mockResolvedValue(undefined)
    await prefetchDashboardStories(queryClient)
    expect(prefetch).toHaveBeenCalledOnce()
  })

  it("exposes the same query through the React hook", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    fetchStoriesMock.mockResolvedValue({ status: 200, data: [story] })
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { result } = renderHook(() => useDashboardStories(), { wrapper })
    await waitFor(() => expect(result.current.data).toEqual([story]))
  })
})
