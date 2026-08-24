import { renderHook } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { NewsItem } from "@/api/news"

const mocks = vi.hoisted(() => ({
  result: { news: undefined, isLoading: false } as {
    news: readonly NewsItem[] | undefined
    isLoading: boolean
  },
  useNewsListQuery: vi.fn(),
  newsListQueryKey: vi.fn(),
}))

vi.mock("@/api/hooks/news", () => ({
  useNewsListQuery: mocks.useNewsListQuery,
  newsListQueryKey: mocks.newsListQueryKey,
}))

import {
  dashboardNewsQueryKey,
  prefetchDashboardNews,
  useDashboardNews,
} from "@/hooks/useDashboardNews"

const news = (id: string, pinned?: boolean | null) =>
  ({ id, title: id, pinned }) as unknown as NewsItem

describe("useDashboardNews", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.result = { news: undefined, isLoading: false }
    mocks.useNewsListQuery.mockImplementation(() => mocks.result)
    mocks.newsListQueryKey.mockImplementation((filters) => ["news", "list", filters])
  })

  it("returns an empty list while preserving the query state", () => {
    const { result, rerender } = renderHook(() => useDashboardNews("ru"))

    expect(result.current).toEqual({ isLoading: false, data: [] })
    expect(mocks.useNewsListQuery).toHaveBeenCalledWith({ language: "ru", limit: 4 })

    mocks.result = { news: [], isLoading: true }
    rerender()
    expect(result.current).toEqual({ isLoading: true, data: [] })
  })

  it("orders pinned items first, removes empty entries, and limits the dashboard", () => {
    mocks.result = {
      news: [
        news("plain"),
        null,
        news("pinned", true),
        news("explicit-false", false),
        news("nullable", null),
        news("overflow", true),
      ] as unknown as NewsItem[],
      isLoading: false,
    }

    const { result } = renderHook(() => useDashboardNews("en"))

    expect(result.current.data).toHaveLength(4)
    expect(result.current.data.slice(0, 2).map((item) => item.id)).toEqual(["pinned", "overflow"])
    expect(result.current.data.map((item) => item.id)).not.toContain("nullable")
  })

  it("exposes the canonical key and resolves the disabled prefetch contract", async () => {
    const queryClient = {} as Parameters<typeof prefetchDashboardNews>[0]

    await expect(prefetchDashboardNews(queryClient, "en")).resolves.toBeUndefined()
    expect(dashboardNewsQueryKey("en")).toEqual(["news", "list", { language: "en", limit: 4 }])
    expect(mocks.newsListQueryKey).toHaveBeenCalledWith({ language: "en", limit: 4 })
  })
})
