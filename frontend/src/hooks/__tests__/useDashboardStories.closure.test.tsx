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
  projectDashboardStories,
  useDashboardStories,
} from "@/hooks/useDashboardStories"

const story: StoryItem = {
  id: "story-1",
  created_at: "2026-01-01T00:00:00.000Z",
  expires_at: "2026-12-31T23:59:59.000Z",
  is_active: true,
  published_at: "2026-01-01T00:00:00.000Z",
  short_text: "Campus preview",
  title: "Campus",
  cover_url: null,
  cover_url_optimized: "https://images.example/campus.webp",
  cta_url: "https://app.example/stories/story-1",
  created_by: "creator-private-sentinel",
  short_text_en: "Private localized preview",
  title_en: "Private localized title",
}
const dashboardStory = {
  id: story.id,
  created_at: story.created_at,
  expires_at: story.expires_at,
  is_active: story.is_active,
  published_at: story.published_at,
  short_text: story.short_text,
  title: story.title,
  cover_url: story.cover_url,
  cover_url_optimized: story.cover_url_optimized,
  cta_url: story.cta_url,
}

const runQuery = async (queryClient: QueryClient, signal?: AbortSignal) => {
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
    fetchStoriesMock.mockResolvedValueOnce({
      data: [story, null, false, { ...story, id: "malformed", expires_at: undefined }],
    })
    await expect(runQuery(queryClient)).resolves.toEqual([dashboardStory])

    fetchStoriesMock.mockResolvedValueOnce({ data: { unexpected: true } })
    await expect(runQuery(queryClient)).resolves.toEqual([])
  })

  it("projects the story display contract and accepts optional null fields", () => {
    expect(projectDashboardStories([story])).toEqual([dashboardStory])
    expect(
      projectDashboardStories([
        {
          id: "optional-story",
          created_at: "2026-01-01T00:00:00.000Z",
          expires_at: "2026-12-31T23:59:59.000Z",
          is_active: false,
          published_at: "2026-01-01T00:00:00.000Z",
          short_text: "Optional",
          title: "Optional fields",
          cover_url: null,
          cover_url_optimized: undefined,
          cta_url: null,
          created_by: "not-transferred",
        },
      ])
    ).toEqual([
      {
        id: "optional-story",
        created_at: "2026-01-01T00:00:00.000Z",
        expires_at: "2026-12-31T23:59:59.000Z",
        is_active: false,
        published_at: "2026-01-01T00:00:00.000Z",
        short_text: "Optional",
        title: "Optional fields",
        cover_url: null,
        cover_url_optimized: undefined,
        cta_url: null,
      },
    ])
    const requiredOnlyStory = {
      id: "required-only",
      created_at: "2026-01-01T00:00:00.000Z",
      expires_at: "2026-12-31T23:59:59.000Z",
      is_active: true,
      published_at: "2026-01-01T00:00:00.000Z",
      short_text: "Required fields only",
      title: "Required only",
    }
    expect(projectDashboardStories([requiredOnlyStory])).toEqual([requiredOnlyStory])

    const invalidRequiredStories: unknown[] = [
      null,
      "not-a-story",
      { ...story, id: 7 },
      { ...story, created_at: null },
      { ...story, expires_at: 7 },
      { ...story, is_active: "yes" },
      { ...story, published_at: false },
      { ...story, short_text: 4 },
      { ...story, title: {} },
    ]
    for (const invalidStory of invalidRequiredStories) {
      expect(projectDashboardStories([invalidStory])).toEqual([])
    }

    expect(projectDashboardStories([{ ...story, cover_url: 7 }])).toEqual([])
    expect(projectDashboardStories([{ ...story, cover_url_optimized: false }])).toEqual([])
    expect(projectDashboardStories([{ ...story, cta_url: {} }])).toEqual([])
    expect(projectDashboardStories([])).toEqual([])
    expect(projectDashboardStories({ items: [story] })).toBeUndefined()
    expect(projectDashboardStories(null)).toBeUndefined()
  })

  it("returns the cached snapshot for 304 and an empty list without a snapshot", async () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(dashboardStoriesQueryKey, [story])
    fetchStoriesMock.mockResolvedValueOnce({ status: 304, data: undefined })
    await expect(runQuery(queryClient)).resolves.toEqual([dashboardStory])

    const emptyClient = new QueryClient()
    fetchStoriesMock.mockResolvedValueOnce({ status: 304, data: undefined })
    await expect(runQuery(emptyClient)).resolves.toEqual([])
  })

  it("falls back to cached data on a non-abort error and rethrows otherwise", async () => {
    const cachedClient = new QueryClient()
    cachedClient.setQueryData(dashboardStoriesQueryKey, [story])
    const recoverable = new Error("temporary failure")
    fetchStoriesMock.mockRejectedValueOnce(recoverable)
    await expect(runQuery(cachedClient)).resolves.toEqual([dashboardStory])

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
    expect(options.placeholderData([dashboardStory])).toEqual([dashboardStory])

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
    await waitFor(() => expect(result.current.data).toEqual([dashboardStory]))
  })
})
