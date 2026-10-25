import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { type PropsWithChildren } from "react"
import { describe, expect, it } from "vitest"
import { newsListQueryKey } from "@/api/hooks/news"
import { type NewsItem } from "@/api/news"
import { useArticleNavigation } from "../useArticleNavigation"

const makeArticle = (id: string, title: string) => ({ id, title }) as unknown as NewsItem

const makeClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })

const makeWrapper = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return Wrapper
}

const articleListKey = newsListQueryKey({ language: "en", limit: 12 })

describe("useArticleNavigation", () => {
  it("returns empty navigation when the current article is absent from cached pages", () => {
    const queryClient = makeClient()
    const { result } = renderHook(() => useArticleNavigation("missing"), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current).toEqual({ prevId: null, nextId: null, prevTitle: null, nextTitle: null })
  })

  it("flattens cached pages, deduplicates IDs, and finds adjacent articles in order", () => {
    const queryClient = makeClient()
    queryClient.setQueryData(newsListQueryKey({ language: "en", limit: 12 }), {
      pages: [
        {
          items: [makeArticle("first", "First"), makeArticle("current", "Current")],
        },
      ],
    })
    queryClient.setQueryData(newsListQueryKey({ language: "ru", limit: 12 }), {
      pages: [
        {
          items: [makeArticle("current", "Duplicate"), makeArticle("last", "Last")],
        },
      ],
    })

    const { result } = renderHook(() => useArticleNavigation("current"), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current).toEqual({
      prevId: "first",
      nextId: "last",
      prevTitle: "First",
      nextTitle: "Last",
    })
  })

  it("handles missing page data and first/last navigation boundaries", () => {
    const queryClient = makeClient()
    queryClient.setQueryData(newsListQueryKey({ language: "en", limit: 12 }), {})
    expect(
      renderHook(() => useArticleNavigation("missing"), {
        wrapper: makeWrapper(queryClient),
      }).result.current
    ).toEqual({ prevId: null, nextId: null, prevTitle: null, nextTitle: null })

    act(() => {
      queryClient.setQueryData(newsListQueryKey({ language: "ru", limit: 12 }), {
        pages: [{}, { items: undefined }],
      })
    })
    expect(
      renderHook(() => useArticleNavigation("missing"), {
        wrapper: makeWrapper(queryClient),
      }).result.current
    ).toEqual({ prevId: null, nextId: null, prevTitle: null, nextTitle: null })

    act(() => {
      queryClient.setQueryData(newsListQueryKey({ language: "de", limit: 12 }), {
        pages: [
          {
            items: [makeArticle("first", "First"), makeArticle("last", "Last")],
          },
        ],
      })
    })
    expect(
      renderHook(() => useArticleNavigation("first"), {
        wrapper: makeWrapper(queryClient),
      }).result.current
    ).toEqual({ prevId: null, nextId: "last", prevTitle: null, nextTitle: "Last" })
    expect(
      renderHook(() => useArticleNavigation("last"), {
        wrapper: makeWrapper(queryClient),
      }).result.current
    ).toEqual({ prevId: "first", nextId: null, prevTitle: "First", nextTitle: null })
  })

  it("ignores cache updates outside the news-list queries", () => {
    const queryClient = makeClient()
    let renderCount = 0
    const { result } = renderHook(
      () => {
        renderCount += 1
        return useArticleNavigation("current")
      },
      { wrapper: makeWrapper(queryClient) }
    )
    const initialRenderCount = renderCount

    act(() => {
      queryClient.setQueryData(["users", "me"], {
        pages: [
          { items: [makeArticle("previous", "Previous"), makeArticle("current", "Current")] },
        ],
      })
    })

    expect(renderCount).toBe(initialRenderCount)
    expect(result.current).toEqual({ prevId: null, nextId: null, prevTitle: null, nextTitle: null })
  })
  it("updates neighbors when news-list data arrives and changes after render", async () => {
    const queryClient = makeClient()
    const { result } = renderHook(() => useArticleNavigation("current"), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current).toEqual({ prevId: null, nextId: null, prevTitle: null, nextTitle: null })

    act(() => {
      queryClient.setQueryData(articleListKey, {
        pages: [
          { items: [makeArticle("previous", "Previous"), makeArticle("current", "Current")] },
        ],
      })
    })

    await waitFor(() => {
      expect(result.current).toEqual({
        prevId: "previous",
        nextId: null,
        prevTitle: "Previous",
        nextTitle: null,
      })
    })

    act(() => {
      queryClient.setQueryData(articleListKey, {
        pages: [
          {
            items: [
              makeArticle("previous", "Previous"),
              makeArticle("current", "Current"),
              makeArticle("next", "Next"),
            ],
          },
        ],
      })
    })

    await waitFor(() => {
      expect(result.current).toEqual({
        prevId: "previous",
        nextId: "next",
        prevTitle: "Previous",
        nextTitle: "Next",
      })
    })
  })
})
